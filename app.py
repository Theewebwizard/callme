"""
Root entrypoint for Hugging Face Spaces (Gradio SDK), Vercel, and Cloud deployments.
Mounts the full FastAPI backend under /api and provides a live health interface.
"""

try:
    import gradio as gr
    from backend.main import app as fastapi_app

    with gr.Blocks(title="CallMe AI Receptionist API") as demo:
        gr.Markdown("# 📞 CallMe AI Receptionist API is LIVE!")
        gr.Markdown("Serving real-time multi-tenant voice receptionist endpoints for CallMe.")
        gr.Markdown("- **Swagger Documentation**: [/docs](/docs)")
        gr.Markdown("- **Health Check**: [/health](/health)")
        gr.Markdown("- **Public Telemetry**: [/api/public/metrics](/api/public/metrics)")

    app = gr.mount_gradio_app(fastapi_app, demo, path="/")
except Exception:
    from backend.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
