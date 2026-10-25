"""
Reusable HTTP API client connecting Streamlit to the FastAPI backend.
Replaces direct database and repository calls from UI components.
"""

from typing import List, Dict, Any, Optional
import httpx

from backend.config import get_settings


class ApiClientError(Exception):
    """Raised when the REST API returns an error response."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ApiConnectionError(ApiClientError):
    """Raised when the API server is offline or unreachable."""
    pass


class ApiNotFoundError(ApiClientError):
    """Raised when a requested resource (e.g. tenant ID or action) is not found."""
    pass


class ApiClient:
    """Client for interacting with the AI Receptionist FastAPI service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.API_BASE_URL).rstrip("/")
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(base_url=self.base_url, timeout=15.0)

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = path if path.startswith("/") else f"/{path}"
        client = self._get_client()
        try:
            # If client was provided externally, don't close it; otherwise use context manager
            if self._client is not None:
                resp = client.request(method, url, json=json, params=params)
            else:
                with client as c:
                    resp = c.request(method, url, json=json, params=params)

            if resp.status_code == 404:
                err_detail = resp.json().get("detail", "Resource not found.") if resp.headers.get("content-type") == "application/json" else resp.text
                raise ApiNotFoundError(err_detail, status_code=404)

            if not resp.is_success:
                try:
                    err_payload = resp.json()
                    detail = err_payload.get("detail", resp.text)
                except Exception:
                    detail = resp.text
                raise ApiClientError(str(detail), status_code=resp.status_code)

            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as conn_err:
            raise ApiConnectionError(
                f"Cannot connect to backend API server at '{self.base_url}'. "
                "Ensure FastAPI is running (uvicorn backend.main:app --port 8000)."
            ) from conn_err
        except (ApiNotFoundError, ApiClientError):
            raise
        except Exception as exc:
            raise ApiClientError(f"API request failed: {type(exc).__name__}: {exc}") from exc

    def health_check(self) -> Dict[str, Any]:
        """Call GET /health."""
        return self._request("GET", "/health")

    def list_businesses(self) -> List[Dict[str, Any]]:
        """Call GET /api/businesses."""
        return self._request("GET", "/api/businesses")

    def get_business(self, business_id: str) -> Dict[str, Any]:
        """Call GET /api/businesses/{business_id}."""
        return self._request("GET", f"/api/businesses/{business_id}")

    def create_business(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Call POST /api/businesses."""
        return self._request("POST", "/api/businesses", json=data)

    def update_business(self, business_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Call PUT /api/businesses/{business_id}."""
        return self._request("PUT", f"/api/businesses/{business_id}", json=updates)

    def delete_business(self, business_id: str) -> Dict[str, Any]:
        """Call DELETE /api/businesses/{business_id}."""
        return self._request("DELETE", f"/api/businesses/{business_id}")

    def list_faqs(self, business_id: str) -> List[Dict[str, Any]]:
        """Call GET /api/businesses/{business_id}/faqs."""
        return self._request("GET", f"/api/businesses/{business_id}/faqs")

    def update_faqs(self, business_id: str, faqs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Call PUT /api/businesses/{business_id}/faqs."""
        return self._request("PUT", f"/api/businesses/{business_id}/faqs", json={"faqs": faqs})

    def get_tools(self, business_id: str) -> Dict[str, Any]:
        """Call GET /api/businesses/{business_id}/tools."""
        return self._request("GET", f"/api/businesses/{business_id}/tools")

    def update_tools(self, business_id: str, tool_statuses: Dict[str, bool]) -> Dict[str, Any]:
        """Call PUT /api/businesses/{business_id}/tools."""
        return self._request("PUT", f"/api/businesses/{business_id}/tools", json={"tool_statuses": tool_statuses})

    def get_call_history(
        self,
        business_id: str,
        outcome: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Call GET /api/businesses/{business_id}/calls."""
        params = {"limit": limit, "offset": offset}
        if outcome:
            params["outcome"] = outcome
        return self._request("GET", f"/api/businesses/{business_id}/calls", params=params)

    def send_playground_message(self, business_id: str, message: str) -> Dict[str, Any]:
        """Call POST /api/businesses/{business_id}/playground/messages."""
        return self._request("POST", f"/api/businesses/{business_id}/playground/messages", json={"message": message})

    def confirm_pending_action(self, business_id: str, action_id: str) -> Dict[str, Any]:
        """Call POST /api/businesses/{business_id}/pending-actions/{action_id}/confirm."""
        return self._request("POST", f"/api/businesses/{business_id}/pending-actions/{action_id}/confirm")

    def cancel_pending_action(self, business_id: str, action_id: str) -> Dict[str, Any]:
        """Call POST /api/businesses/{business_id}/pending-actions/{action_id}/cancel."""
        return self._request("POST", f"/api/businesses/{business_id}/pending-actions/{action_id}/cancel")


_DEFAULT_API_CLIENT: Optional[ApiClient] = None


def get_api_client() -> ApiClient:
    """Retrieve singleton ApiClient."""
    global _DEFAULT_API_CLIENT
    if _DEFAULT_API_CLIENT is None:
        _DEFAULT_API_CLIENT = ApiClient()
    return _DEFAULT_API_CLIENT


def set_api_client(client: ApiClient) -> None:
    """Override singleton client (useful for testing or in-process simulation)."""
    global _DEFAULT_API_CLIENT
    _DEFAULT_API_CLIENT = client
