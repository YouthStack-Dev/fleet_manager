from dotenv import load_dotenv
load_dotenv()

import os
import logging
import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_admin import db

logger = logging.getLogger(__name__)

firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "/app/app/firebase/firebase_key.json")

# For local development/testing, try alternate paths
if not os.path.exists(firebase_key_path):
    local_path = os.path.join(os.path.dirname(__file__), "firebase_key.json")
    if os.path.exists(local_path):
        firebase_key_path = local_path
    else:
        import sys
        if 'pytest' not in sys.modules:
            raise FileNotFoundError(f"Firebase key not found at: {firebase_key_path}. "
                                    "Check your docker-compose volume mount.")


def init_firebase():
    """
    Initialise Firebase Admin SDK.

    Logs a clear diagnostic so you can immediately see whether RTDB and FCM
    will work — no silent failures at startup.
    """
    rtdb_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()

    # ── Key file check ────────────────────────────────────────────────────────
    if not os.path.exists(firebase_key_path):
        logger.error(
            "[Firebase] ❌ KEY FILE MISSING — path: %s  "
            "→ RTDB writes AND FCM pushes will be SKIPPED until this is fixed.",
            firebase_key_path,
        )
        raise FileNotFoundError(f"Firebase key not found at: {firebase_key_path}")

    logger.info("[Firebase] ✅ Key file found: %s", firebase_key_path)

    # ── RTDB URL check ────────────────────────────────────────────────────────
    if not rtdb_url:
        logger.warning(
            "[Firebase] ⚠️  FIREBASE_DATABASE_URL is not set  "
            "→ Firebase Admin SDK will initialise (FCM will work) "
            "but ALL Realtime Database writes will FAIL. "
            "Set FIREBASE_DATABASE_URL=https://<project>-default-rtdb.firebaseio.com "
            "to enable live chat updates."
        )
    else:
        logger.info("[Firebase] ✅ RTDB URL configured: %s", rtdb_url)

    # ── Initialise SDK (idempotent) ───────────────────────────────────────────
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_key_path)
            initialize_app(cred, {"databaseURL": rtdb_url or None})
            logger.info(
                "[Firebase] ✅ Admin SDK initialised — FCM: ready | RTDB: %s",
                "ready" if rtdb_url else "DISABLED (no RTDB URL)",
            )

            # ── Pre-warm OAuth2 credentials ───────────────────────────────
            # The google-auth library fetches an access token lazily on the
            # first RTDB/FCM call, adding ~80-100 ms to that request.
            # Calling get_access_token() here at startup caches the token
            # for its 1-hour lifetime so the first background task runs
            # without a blocking OAuth2 round-trip.
            try:
                app = firebase_admin.get_app()
                token_info = app.credential.get_access_token()
                logger.info(
                    "[Firebase] ✅ OAuth2 token pre-warmed — expires at %s",
                    token_info.expiry,
                )
            except Exception as warm_err:
                logger.warning(
                    "[Firebase] ⚠️  OAuth2 pre-warm failed (non-fatal): %s  "
                    "→ First RTDB/FCM call will still refresh automatically.",
                    warm_err,
                )
        else:
            logger.debug("[Firebase] Admin SDK already initialised — skipping re-init.")
    except Exception as e:
        logger.error("[Firebase] ❌ Admin SDK init FAILED: %s", e)
        raise
