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
from backend.api import api_router
from backend.main import (
    app as fastapi_app,
    health_check,
    get_public_platform_metrics,
)

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    # Launch Gradio server without thread lock so we can attach FastAPI routes to demo.server_app
    demo.launch(prevent_thread_lock=True, server_name="0.0.0.0", server_port=port, ssr_mode=False)

    # Attach all FastAPI endpoints to the active server application
    demo.server_app.include_router(api_router, prefix="/api")
    demo.server_app.add_api_route("/health", health_check, methods=["GET"])
    demo.server_app.add_api_route("/api/health", health_check, methods=["GET"])
    demo.server_app.add_api_route("/api/public/metrics", get_public_platform_metrics, methods=["GET"])
    demo.server_app.add_api_route("/api/platform/metrics", get_public_platform_metrics, methods=["GET"])

    existing_paths = {getattr(r, "path", None) for r in demo.server_app.routes}
    for route in fastapi_app.routes:
        if getattr(route, "path", None) not in existing_paths:
            demo.server_app.routes.append(route)

    # Block main thread to keep application alive and responsive
    demo.block()
