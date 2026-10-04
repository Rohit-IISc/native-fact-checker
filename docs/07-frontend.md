# 07. Frontend (PWA)

React + Vite + TypeScript, `vite-plugin-pwa` (injectManifest mode, custom service worker), Firebase JS SDK, `i18next`. Mobile-first, works on desktop for judges.

## Web Share Target

`manifest.webmanifest`:

```json
{
  "name": "<App name>",
  "short_name": "<App name>",
  "start_url": "/",
  "display": "standalone",
  "share_target": {
    "action": "/share-target",
    "method": "POST",
    "enctype": "multipart/form-data",
    "params": {
      "title": "title",
      "text": "text",
      "url": "url",
      "files": [{ "name": "files", "accept": ["image/*", "video/*", "audio/*", ".opus", ".ogg"] }]
    }
  }
}
```

The service worker intercepts `POST /share-target`, stores the FormData in IndexedDB (browsers forbid a page from reading it directly), redirects to `/check?shared=1`. The page reads it, signs the user in if needed, and posts to `/api/v1/checks`. WhatsApp often puts a link inside `text` rather than `url`: extract URLs from `text` on the client and on the server.

The app appears in the Android share sheet only after the user installs it (Add to Home screen). The home screen shows an install banner with a 3-step visual guide. Android Chrome only for the share target; iOS and desktop users use paste or upload.

## Screens

1. Welcome and consent (first run): what the app does, that media is deleted within 24 hours, Google sign-in button
2. Home: paste box, upload button, "How to share from WhatsApp" guide, quota left today, recent checks
3. Check (live progress): a vertical step list driven by the Firestore snapshot (Received, Looking for earlier checks, Opening link, Reading the post, Searching news and fact-checkers, Checking the source, Checking where the image came from, Weighing evidence, Second opinion, Writing your answer, Recording audio). Each sub-agent ticks as it finishes. Show a "you can leave this screen, we will notify you" note after 10 s
4. Result: verdict badge (colors: TRUE green, FALSE red, MISLEADING orange, SCAM purple, NOT_ENOUGH_EVIDENCE grey), confidence, headline and summary in the content language, audio player, "What is true", "Evidence for" and "Evidence against" lists, sources with domain and link, English toggle, buttons: Share card to WhatsApp (Web Share API with the PNG file), Copy result link, Was this helpful
5. History: list of past checks with label chips
6. Public result page `/r/{verdict_id}`: same as result without user data, with an "Check your own forward" call to action
7. Limit reached: friendly message in UI language with reset time

## Push

Firebase Cloud Messaging for web. Ask notification permission after the first check starts (not on first load). Store token via `POST /v1/me/fcm-token`. Notification text in the UI language: "Result ready: {label}". Tapping opens `/check/{check_id}`.

## Language

UI strings in `src/i18n/{en,hi,ta,kn,id}.json`. Verdict content comes from the backend in the content language. Fonts: Noto Sans plus Noto Sans Devanagari, Tamil and Kannada via Google Fonts with Latin fallback.

## Accessibility

Large tap targets (48 px), audio first for low-literacy users (big play button at the top of the result), high-contrast colors, no information conveyed by color alone (label text always shown).
