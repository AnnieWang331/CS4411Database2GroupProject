// Where the web client finds the APIs. These defaults are scripts/serve_local.py's.
// scripts/deploy_web.py uploads its own copy of this file with the stack's URLs, so the
// deployed site talks to the deployed APIs and this file never has to be edited.
export const API_URL = "http://127.0.0.1:3000";
export const WS_URL = "ws://127.0.0.1:3001";
