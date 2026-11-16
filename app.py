"""
Root entrypoint for Hugging Face Spaces (Gradio SDK + ZeroGPU) and Cloud deployments.
Exposes full FastAPI backend routes and Gradio diagnostics UI.
"""
import os
import sys

# Safe import for Hugging Face ZeroGPU compatibility
try:
    import spaces
except ImportError:
    class _SpacesMock:
        @staticmethod
        def GPU(fn=None, **kwargs):
            if fn is None:
                return lambda f: f
            return fn
    spaces = _SpacesMock()

@spaces.GPU
def check_engine_status(prompt: str = "operational") -> str:
    """Hugging Face ZeroGPU heartbeat hook."""
    return f"CallMe AI Receptionist ZeroGPU Engine is active ({prompt})"

import gradio as gr
from fastapi.middleware.cors import CORSMiddleware
from backend.main import app as fastapi_app

with gr.Blocks(title="CallMe AI Receptionist API") as demo:
    gr.Markdown("# 📞 CallMe AI Receptionist API is LIVE!")
    gr.Markdown("Serving real-time multi-tenant voice receptionist endpoints for CallMe.")
    gr.Markdown("- **Health Check**: [/health](/health)")
    gr.Markdown("- **Public Telemetry**: [/api/public/metrics](/api/public/metrics)")

    with gr.Row():
        status_input = gr.Textbox(value="ping", label="Diagnostics Input")
        status_output = gr.Textbox(label="Diagnostics Output")
    status_btn = gr.Button("Test Diagnostics Endpoint")
    status_btn.click(fn=check_engine_status, inputs=status_input, outputs=status_output)

# Attach all FastAPI routes to demo.app so all /health and /api endpoints are served
for route in fastapi_app.routes:
    demo.app.routes.append(route)

# Add CORS middleware to support Vercel frontend requests
demo.app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = demo.app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
