"""
IoT routes (WebSocket API Key auth via X-API-Key header):
  WS /iot/stream?device_id={device_id} — Real-time audio streaming (raw PCM)
"""
import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.dependencies import DB, AppSettings
from app.services.iot_service import IoTService
from app.services.audio_manager import AudioManager
from app.models.iot import IoTMessage, IoTMessageRole

import httpx
from google import genai
from google.genai import types

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/stream")
async def iot_stream(
    websocket: WebSocket,
    device_id: str,
    db: DB,
    settings: AppSettings,
):
    """
    WebSocket endpoint for real-time audio streaming (Raw PCM).
    Authenticates via X-API-Key header and auto-creates an IoT session.
    """
    # 1. Authenticate via X-API-Key header
    api_key = websocket.headers.get("x-api-key")
    if not api_key or api_key != settings.iot_api_key:
        logger.warning(f"Connection rejected: Invalid or missing X-API-Key header")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Verify device_id is provided
    if not device_id:
        logger.warning("Connection rejected: Missing device_id parameter")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info(f"WebSocket connection accepted for device {device_id}")

    # 3. Auto-initialize session
    try:
        service = IoTService(db, settings)
        session = await service.create_session(device_id)
        sid = session.id
        logger.info(f"Created IoT session {sid} for device {device_id}")
    except Exception as e:
        logger.error(f"Failed to create IoT session: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # Load local FAQ contexts for Fast Route
    try:
        import os
        with open("faq.txt", "r", encoding="utf-8") as f:
            faq_text = f.read()
    except Exception:
        faq_text = ""

    try:
        while True:
            # Receive raw audio bytes from client
            audio_bytes = await websocket.receive_bytes()
            
            # Transcribe raw audio to text
            transcription = await AudioManager.transcribe(audio_bytes)
            if not transcription.strip():
                continue

            logger.info(f"[{device_id}] Transcribed user input: {transcription}")

            # Fast Route (FAQ local using lightweight Gemini LLM)
            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = (
                f"Konteks FAQ: {faq_text}\n\nPertanyaan: {transcription}\n"
                "Jawab berdasarkan FAQ. Jika konteks tidak cukup, jawab persis: 'Saya tidak tahu'."
            )
            
            response = await client.aio.models.generate_content(
                model=settings.gemini_llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            answer = response.text.strip()
            
            route_taken = "fast_faq"
            
            # Slow Route Fallback (Full RAG inference)
            if "tidak tahu" in answer.lower():
                route_taken = "slow_rag"
                try:
                    headers = {}
                    if settings.hf_token:
                        headers["Authorization"] = f"Bearer {settings.hf_token}"
                        
                    async with httpx.AsyncClient(headers=headers, timeout=60.0) as http_client:
                        res = await http_client.post(
                            f"{settings.inference_base_url.rstrip('/')}/api/chat",
                            json={"query": transcription}
                        )
                        if res.status_code == 200:
                            data = res.json()
                            answer = data.get("answer", "Maaf, sistem AI sedang sibuk.")
                        else:
                            answer = "Maaf, terjadi kesalahan pada AI engine."
                except Exception as e:
                    logger.error(f"Failed to connect to RAG inference engine: {e}")
                    answer = "Maaf, mesin inferensi sedang tidak dapat dihubungi."

            logger.info(f"[{device_id}] Responding ({route_taken}): {answer}")

            # Synthesize answer back to speech (TTS)
            audio_response = await AudioManager.synthesize(answer)
            
            # Save messages in history
            user_msg = IoTMessage(
                iot_session_id=sid,
                role=IoTMessageRole.user,
                content=transcription,
                meta={"route": route_taken}
            )
            assistant_msg = IoTMessage(
                iot_session_id=sid,
                role=IoTMessageRole.assistant,
                content=answer,
                meta={"route": route_taken}
            )
            db.add_all([user_msg, assistant_msg])
            await db.commit()
            
            # Send synthesized audio response back to device
            await websocket.send_bytes(audio_response)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device {device_id}")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass

