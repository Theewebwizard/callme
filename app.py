"""
Root entrypoint for Hugging Face Spaces (Gradio SDK + ZeroGPU), Vercel, and Cloud deployments.
Mounts the full FastAPI backend under /api and provides a live health interface.
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
    """Hugging Face ZeroGPU heartbeat function."""
    return f"CallMe AI Receptionist Engine is active ({prompt})"

try:
    import gradio as gr
    from backend.main import app as fastapi_app

    with gr.Blocks(title="CallMe AI Receptionist API") as demo:
        gr.Markdown("# 📞 CallMe AI Receptionist API is LIVE!")
        gr.Markdown("Serving real-time multi-tenant voice receptionist endpoints for CallMe.")
        gr.Markdown("- **Swagger Documentation**: [/docs](/docs)")
        gr.Markdown("- **Health Check**: [/health](/health)")
        gr.Markdown("- **Public Telemetry**: [/api/public/metrics](/api/public/metrics)")

        with gr.Row():
            status_input = gr.Textbox(value="ping", label="Diagnostics Input")
            status_output = gr.Textbox(label="Diagnostics Output")
        status_btn = gr.Button("Test Diagnostics Endpoint")
        status_btn.click(fn=check_engine_status, inputs=status_input, outputs=status_output)

    app = gr.mount_gradio_app(fastapi_app, demo, path="/")
except Exception as e:
    from backend.main import app

__all__ = ["app", "check_engine_status"]

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
