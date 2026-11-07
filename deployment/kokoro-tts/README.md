# Shared classroom voice

Deploy this directory as a small, private CPU service next to the Lyo API.
It runs Kokoro-82M behind an OpenAI-compatible speech endpoint.

Configure the main API with:

```env
TTS_PROVIDER=kokoro
KOKORO_TTS_BASE_URL=http://<private-kokoro-host>:8880
TTS_DEFAULT_LANGUAGE=en-US
TTS_CACHE_TTL_HOURS=168
ALLOW_OPENAI_TTS=false
```

The API selects `af_heart` for English and `ef_dora` for Spanish. It renders
and caches each short teaching turn once, then returns that identical audio to
Web, iOS, and Android.

To trial a managed voice instead, explicitly set `TTS_PROVIDER=google` and
provide a dedicated OAuth credential via `GOOGLE_TTS_SERVICE_ACCOUNT_JSON` or
`GOOGLE_APPLICATION_CREDENTIALS`, along with the staging-only trial budget flags.
This is never used as an automatic fallback. OpenAI TTS
also remains disabled unless both `TTS_PROVIDER=openai` and
`ALLOW_OPENAI_TTS=true` are set.
