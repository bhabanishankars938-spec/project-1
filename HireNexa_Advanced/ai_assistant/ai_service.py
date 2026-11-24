import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Generator, Iterator
import httpx
from django.conf import settings
from .prompts import build_system_prompt
from .tools import HireNexaToolRegistry
from .web_research import WebResearchService
from .knowledge_engine import TechnicalKnowledgeEngine

logger = logging.getLogger(__name__)


# ==============================================================================
# EXCEPTIONS FOR HYBRID PROVIDER ROUTING
# ==============================================================================

class AIProviderError(Exception):
    """Base exception for AI provider operations."""
    pass


class AuthenticationError(AIProviderError):
    """Raised when provider rejects credentials (HTTP 401/403). Ineligible for fallback."""
    pass


class BadRequestError(AIProviderError):
    """Raised on invalid request schema or unsupported parameter."""
    pass


class TemporaryProviderError(AIProviderError):
    """Eligible temporary failure (429 Rate Limit, 5xx Server Error, Timeout, Network Failure)."""
    pass


class OllamaUnavailableError(AIProviderError):
    """Raised when Ollama fallback service cannot be reached."""
    pass


class ConfigurationError(AIProviderError):
    """Raised when required configuration is missing from backend environment."""
    pass


# ==============================================================================
# PROVIDER INTERFACE & IMPLEMENTATIONS
# ==============================================================================

class BaseLLMProvider(ABC):
    """Provider-independent interface for LLM services."""

    def __init__(self, name: str, model: str):
        self.name = name
        self.model = model

    @abstractmethod
    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        """Streams text chunks from provider."""
        pass

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Checks if provider is configured and reachable."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """
    Primary Provider: OpenAI API (or OpenAI-compatible gateways).
    Reads API credentials securely from backend environment variables.
    """

    def __init__(self):
        model = getattr(settings, "OPENAI_MODEL", "") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        super().__init__(name="openai", model=model)
        self.api_key = (getattr(settings, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")).strip()
        self.base_url = (getattr(settings, "OPENAI_BASE_URL", "") or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = float(getattr(settings, "AI_REQUEST_TIMEOUT", 30.0))

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "OPENAI_API_KEY is not set in backend environment variables."
        return True, "OpenAI API configured"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise ConfigurationError("OPENAI_API_KEY is not configured in backend environment.")

        endpoint = f"{self.base_url}/chat/completions"

        # Build messages list
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        # Multimodal vision support
        if image_attachment and image_attachment.get("base64_data"):
            b64 = image_attachment["base64_data"]
            mtype = image_attachment.get("mime_type", "image/jpeg")
            content_list = [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mtype};base64,{b64}"}},
            ]
            messages.append({"role": "user", "content": content_list})
        else:
            messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": float(getattr(settings, "AI_TEMPERATURE", 0.7)),
            "max_tokens": int(getattr(settings, "AI_MAX_TOKENS", 4096)),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                    status = response.status_code

                    # Classify errors strictly
                    if status == 401 or status == 403:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.error("OpenAI Authentication Error (HTTP %d): %s", status, err_body)
                        raise AuthenticationError(
                            f"OpenAI Authentication Failed (HTTP {status}): Invalid or unauthorized API key. "
                            f"Please verify OPENAI_API_KEY in your backend .env file."
                        )
                    elif status == 429:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.warning("OpenAI Rate Limit / Quota Exceeded (HTTP 429): %s", err_body)
                        raise TemporaryProviderError("OpenAI rate limit or usage quota exceeded (HTTP 429).")
                    elif status >= 500:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.warning("OpenAI Server Error (HTTP %d): %s", status, err_body)
                        raise TemporaryProviderError(f"OpenAI service unavailable (HTTP {status}).")
                    elif status >= 400:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.error("OpenAI Bad Request (HTTP %d): %s", status, err_body)
                        raise BadRequestError(f"OpenAI API error (HTTP {status}): {err_body}")

                    # Stream text deltas
                    for line in response.iter_lines():
                        if line.startswith("data: ") and line.strip() != "data: [DONE]":
                            data_str = line[6:].strip()
                            if data_str:
                                try:
                                    chunk = json.loads(data_str)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content")
                                        if content:
                                            yield content
                                except Exception:
                                    pass

        except (httpx.ConnectError, httpx.NetworkError) as e:
            logger.warning("OpenAI Network Connection Failed: %s", e)
            raise TemporaryProviderError(f"Network error connecting to OpenAI endpoint: {e}")
        except httpx.TimeoutException as e:
            logger.warning("OpenAI Request Timed Out: %s", e)
            raise TemporaryProviderError(f"OpenAI request timed out after {self.timeout}s.")


class GeminiProvider(BaseLLMProvider):
    """
    Optional Provider: Google AI Studio / Gemini API (https://aistudio.google.com/).
    Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={key}&alt=sse
    """

    def __init__(self):
        model = getattr(settings, "GEMINI_MODEL", "") or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()
        super().__init__(name="gemini", model=model)
        self.api_key = (
            getattr(settings, "GEMINI_API_KEY", "") or
            os.environ.get("GEMINI_API_KEY", "") or
            getattr(settings, "GOOGLE_API_KEY", "") or
            os.environ.get("GOOGLE_API_KEY", "")
        ).strip()
        self.timeout = float(getattr(settings, "AI_REQUEST_TIMEOUT", 30.0))

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "GEMINI_API_KEY is not set in backend environment variables."
        return True, "Google Gemini API configured"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise ConfigurationError("GEMINI_API_KEY is not configured in backend environment.")

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"

        contents = []
        for msg in history[-10:]:
            role = "user" if msg.get("role") in ["user", "human"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        user_parts = []
        if image_attachment and image_attachment.get("base64_data"):
            user_parts.append({
                "inline_data": {
                    "mime_type": image_attachment.get("mime_type", "image/jpeg"),
                    "data": image_attachment["base64_data"],
                }
            })
        user_parts.append({"text": user_prompt})
        contents.append({"role": "user", "parts": user_parts})

        payload = {
            "contents": contents,
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "generation_config": {
                "temperature": float(getattr(settings, "AI_TEMPERATURE", 0.7)),
                "max_output_tokens": int(getattr(settings, "AI_MAX_TOKENS", 4096)),
            }
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint, json=payload) as response:
                    status = response.status_code
                    if status in (401, 403):
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.error("Gemini Authentication Error (HTTP %d): %s", status, err_body)
                        raise AuthenticationError(
                            f"Google Gemini Authentication Failed (HTTP {status}): Invalid API key. "
                            f"Please verify GEMINI_API_KEY from https://aistudio.google.com/ in your backend .env file."
                        )
                    elif status == 429:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.warning("Gemini Quota Exceeded (HTTP 429): %s", err_body)
                        raise TemporaryProviderError("Google Gemini rate limit or quota exceeded (HTTP 429).")
                    elif status >= 500:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.warning("Gemini Server Error (HTTP %d): %s", status, err_body)
                        raise TemporaryProviderError(f"Google Gemini service unavailable (HTTP {status}).")
                    elif status >= 400:
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.error("Gemini Bad Request (HTTP %d): %s", status, err_body)
                        raise BadRequestError(f"Google Gemini API error (HTTP {status}): {err_body}")

                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str:
                                try:
                                    chunk = json.loads(data_str)
                                    for cand in chunk.get("candidates", []):
                                        for part in cand.get("content", {}).get("parts", []):
                                            text = part.get("text")
                                            if text:
                                                yield text
                                except Exception:
                                    pass

        except (httpx.ConnectError, httpx.NetworkError) as e:
            logger.warning("Gemini Network Connection Failed: %s", e)
            raise TemporaryProviderError(f"Network error connecting to Gemini endpoint: {e}")
        except httpx.TimeoutException as e:
            logger.warning("Gemini Request Timed Out: %s", e)
            raise TemporaryProviderError(f"Gemini request timed out after {self.timeout}s.")


class OllamaProvider(BaseLLMProvider):
    """
    Fallback Provider: Ollama (runs locally or on a private network server).
    Supports streaming chat and vision models.
    """

    def __init__(self):
        model = getattr(settings, "OLLAMA_MODEL", "") or os.environ.get("OLLAMA_MODEL", "llama3.2").strip()
        super().__init__(name="ollama", model=model)
        self.base_url = (getattr(settings, "OLLAMA_BASE_URL", "") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = float(getattr(settings, "AI_REQUEST_TIMEOUT", 45.0))

    def is_available(self) -> tuple[bool, str]:
        """Pings Ollama server endpoint."""
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/api/version")
                if resp.status_code == 200:
                    ver_data = resp.json()
                    return True, f"Ollama online (v{ver_data.get('version', 'unknown')})"
                return False, f"Ollama returned HTTP {resp.status_code}"
        except Exception:
            return False, f"Ollama unreachable at {self.base_url}"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        endpoint = f"{self.base_url}/api/chat"

        # Build messages list in Ollama format
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        user_msg = {"role": "user", "content": user_prompt}
        if image_attachment and image_attachment.get("base64_data"):
            user_msg["images"] = [image_attachment["base64_data"]]
        messages.append(user_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": float(getattr(settings, "AI_TEMPERATURE", 0.7)),
                "num_predict": int(getattr(settings, "AI_MAX_TOKENS", 4096)),
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint, json=payload) as response:
                    if response.status_code != 200:
                        err_body = response.read().decode("utf-8", errors="replace")
                        raise OllamaUnavailableError(f"Ollama returned HTTP {response.status_code}: {err_body}")

                    for line in response.iter_lines():
                        if line.strip():
                            try:
                                chunk = json.loads(line)
                                msg_chunk = chunk.get("message", {})
                                content = msg_chunk.get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass

        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise OllamaUnavailableError(f"Cannot connect to Ollama at {self.base_url}. Service is not running.")
        except httpx.TimeoutException:
            raise OllamaUnavailableError(f"Ollama request timed out after {self.timeout}s.")



class GroqProvider(BaseLLMProvider):
    """
    Optional High-Speed Cloud Provider: Groq (https://groq.com/).
    Uses OpenAI-compatible endpoint with fast inference on Llama 3 models.
    """

    def __init__(self):
        model = getattr(settings, "GROQ_MODEL", "") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        super().__init__(name="groq", model=model)
        self.api_key = (getattr(settings, "GROQ_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")).strip()
        self.base_url = (getattr(settings, "GROQ_BASE_URL", "") or os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")).rstrip("/")
        self.timeout = float(getattr(settings, "AI_REQUEST_TIMEOUT", 30.0))

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "GROQ_API_KEY is not set in backend environment variables."
        return True, "Groq API configured"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise ConfigurationError("GROQ_API_KEY is not configured in backend environment.")

        endpoint = f"{self.base_url}/chat/completions"
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": float(getattr(settings, "AI_TEMPERATURE", 0.7)),
            "max_tokens": int(getattr(settings, "AI_MAX_TOKENS", 4096)),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                    status = response.status_code
                    if status in (401, 403):
                        err_body = response.read().decode("utf-8", errors="replace")
                        logger.error("Groq Authentication Error (HTTP %d): %s", status, err_body)
                        raise AuthenticationError(
                            f"Groq Authentication Failed (HTTP {status}): Invalid API key. "
                            f"Please verify GROQ_API_KEY in your backend .env file."
                        )
                    elif status == 429:
                        raise TemporaryProviderError("Groq rate limit exceeded (HTTP 429).")
                    elif status >= 500:
                        raise TemporaryProviderError(f"Groq service unavailable (HTTP {status}).")
                    elif status >= 400:
                        err_body = response.read().decode("utf-8", errors="replace")
                        raise BadRequestError(f"Groq API error (HTTP {status}): {err_body}")

                    for line in response.iter_lines():
                        if line.startswith("data: ") and line.strip() != "data: [DONE]":
                            data_str = line[6:].strip()
                            if data_str:
                                try:
                                    chunk = json.loads(data_str)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content")
                                        if content:
                                            yield content
                                except Exception:
                                    pass
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise TemporaryProviderError(f"Network error connecting to Groq endpoint: {e}")
        except httpx.TimeoutException:
            raise TemporaryProviderError(f"Groq request timed out after {self.timeout}s.")


class AnthropicProvider(BaseLLMProvider):
    """
    Optional Provider: Anthropic Claude API (https://console.anthropic.com/).
    """

    def __init__(self):
        model = getattr(settings, "ANTHROPIC_MODEL", "") or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()
        super().__init__(name="anthropic", model=model)
        self.api_key = (getattr(settings, "ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
        self.base_url = "https://api.anthropic.com/v1"
        self.timeout = float(getattr(settings, "AI_REQUEST_TIMEOUT", 30.0))

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "ANTHROPIC_API_KEY is not set in backend environment variables."
        return True, "Anthropic Claude API configured"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise ConfigurationError("ANTHROPIC_API_KEY is not configured in backend environment.")

        endpoint = f"{self.base_url}/messages"
        messages = []
        for msg in history[-10:]:
            role = "user" if msg.get("role") in ["user", "human"] else "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": int(getattr(settings, "AI_MAX_TOKENS", 4096)),
            "stream": True,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                    status = response.status_code
                    if status in (401, 403):
                        raise AuthenticationError(f"Anthropic Authentication Failed (HTTP {status}). Check ANTHROPIC_API_KEY.")
                    elif status == 429:
                        raise TemporaryProviderError("Anthropic rate limit exceeded (HTTP 429).")
                    elif status >= 500:
                        raise TemporaryProviderError(f"Anthropic server error (HTTP {status}).")
                    elif status >= 400:
                        err_body = response.read().decode("utf-8", errors="replace")
                        raise BadRequestError(f"Anthropic API error (HTTP {status}): {err_body}")

                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str:
                                try:
                                    event = json.loads(data_str)
                                    etype = event.get("type")
                                    if etype == "content_block_delta":
                                        delta = event.get("delta", {})
                                        if delta.get("type") == "text_delta":
                                            yield delta.get("text", "")
                                except Exception:
                                    pass
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise TemporaryProviderError(f"Network error connecting to Anthropic: {e}")
        except httpx.TimeoutException:
            raise TemporaryProviderError(f"Anthropic request timed out after {self.timeout}s.")


class LocalPlatformIntelligenceProvider(BaseLLMProvider):
    """
    Built-in HireNexa Platform Intelligence Provider.
    Operates without external API keys to synthesize verified real database queries
    (jobs, applications, skill gaps, freelance projects, MCA entrance prep, candidates, analytics)
    and provide structured, transparent answers.
    """

    def __init__(self):
        super().__init__(name="local", model="hirenexa-platform-v2")

    def is_available(self) -> tuple[bool, str]:
        return True, "HireNexa Platform Intelligence (Local Native Engine)"

    def generate_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        image_attachment: dict | None = None,
    ) -> Iterator[str]:
        content_blocks = []

        # Extract clean user inquiry if wrapped in prompt framing
        clean_inquiry = user_prompt
        if "User Inquiry:" in user_prompt:
            clean_inquiry = user_prompt.split("User Inquiry:")[-1].split("[HireNexa Platform")[0].strip()
        elif "[HireNexa Platform Database Tool Results]:" in user_prompt:
            clean_inquiry = user_prompt.split("[HireNexa Platform Database Tool Results]:")[0].strip()

        # Check built-in Technical Knowledge Engine for coding, interview, and architecture questions
        tech_response = TechnicalKnowledgeEngine.get_technical_response(clean_inquiry)
        if tech_response:
            content_blocks.append(tech_response)

        if "[HireNexa Platform Database Tool Results]:" in user_prompt:
            if tech_response:
                content_blocks.append("\n\n---\n\n")
            content_blocks.append("### ⚡ HireNexa Verified Platform Results\n\n")
            content_blocks.append("Here is the verified data retrieved directly from the HireNexa platform database:\n\n")

            if "search_jobs" in user_prompt:
                if '"count": 0' in user_prompt:
                    content_blocks.append("I queried the active vacancies database. There are currently **0 active openings** matching that specific query and location in the live database.\n\n**Suggestions:**\n- Explore all verified positions across India and Remote at **[Find Jobs](/jobs/)**.\n- Broaden your search criteria or register for job alert notifications.\n\n")
                else:
                    content_blocks.append("I queried the active vacancies database. Matching verified openings have been retrieved and presented in the interactive job card above. You can click **View & Apply** on any opening to inspect the job description, eligibility, and submit your application.\n\n")
                    content_blocks.append("**Recommended Next Steps:**\n")
                    content_blocks.append("1. Tailor your resume summary for the key tech stack mentioned in the job.\n")
                    content_blocks.append("2. Complete relevant MCQs on the HireNexa Assessment portal to earn a verified skill badge.\n")
                    content_blocks.append("3. Track the status of your submitted applications directly on your Candidate Dashboard.\n\n")

            elif "search_freelance_projects" in user_prompt:
                content_blocks.append("The HireNexa Project Marketplace was searched for matching contracts and gigs. Verified project listings are rendered above with budget ranges, client ratings, and required skills.\n\n")
                content_blocks.append("**How to Win Freelance Contracts on HireNexa:**\n")
                content_blocks.append("- Submit a concise, customized proposal focusing on the client's explicit requirements.\n")
                content_blocks.append("- Link your verified GitHub repositories and portfolio live demos.\n")
                content_blocks.append("- Define clear milestone deliverables and realistic timelines.\n")

            elif "get_mca_prep_info" in user_prompt:
                content_blocks.append("The MCA Entrance Preparation engine retrieved active syllabus structures, exam benchmarks (NIMCET, OJEE MCA, CUET-PG), and practice questions from the learning repository.\n\n")
                content_blocks.append("**Key Subject Weightage Breakdown:**\n")
                content_blocks.append("- **Mathematics (50% weight in NIMCET):** Coordinate Geometry, Probability, Calculus, Vector Algebra.\n")
                content_blocks.append("- **Computer Awareness (20% weight):** Data Representation, Binary/Hex conversions, Operating Systems, C/C++ fundamentals, DBMS fundamentals.\n")
                content_blocks.append("- **Analytical Ability & Logical Reasoning (20% weight):** Puzzles, Sequences, Blood Relations.\n")
                content_blocks.append("- **General English (10% weight):** Comprehension, Vocabulary, Sentence Completion.\n\n")
                content_blocks.append("👉 Visit the **[HireNexa MCA Entrance Prep Portal](/assessments/entrance-prep/)** to start timed mock exams and track your weak topics.\n")

            elif "get_my_applications" in user_prompt:
                content_blocks.append("Your personal application history was retrieved from the Applicant Tracking System. Your active rounds and current progression are displayed above.\n")

            elif "analyze_candidate_resume" in user_prompt:
                content_blocks.append("Resume diagnostic completed! The platform evaluated your profile against market competency benchmarks. Review the match percentage and missing skill recommendations highlighted above.\n")

            elif "get_admin_governance_summary" in user_prompt:
                content_blocks.append("Platform administration metrics retrieved. Verified counts for active vacancies, registered candidates, recruiters, companies, and verified revenue are displayed in the governance card.\n")

            elif "search_candidates" in user_prompt:
                content_blocks.append("Candidate directory searched. Verified candidate profiles matching your search criteria are listed above with their skills, university, and academic details.\n")

            else:
                content_blocks.append("The requested platform information was successfully retrieved and formatted above.\n")

            content_blocks.append("\n> 💡 *HireNexa Platform Intelligence: Serving verified database records.*")

        elif not tech_response:
            content_blocks.append("### ⚡ HireNexa Intelligent Assistant\n\n")
            content_blocks.append(f"Regarding your inquiry: **\"{clean_inquiry}\"**\n\n")
            content_blocks.append("HireNexa AI operates with built-in domain intelligence across recruitment, engineering, and career acceleration:\n\n")
            content_blocks.append("- 💼 **Job Search:** *\"Find Python developer jobs in Bhubaneswar\"*\n")
            content_blocks.append("- 💻 **Technical Explanations:** *\"Explain Python decorators\"*, *\"Explain async/await\"*, *\"What is binary search?\"*\n")
            content_blocks.append("- 🎯 **Interview Preparation:** *\"Give me 20 Django interview questions\"*, *\"20 Python interview questions\"*\n")
            content_blocks.append("- 📋 **Application Tracking:** *\"What is my application status?\"*\n")
            content_blocks.append("- ✨ **Resume Diagnostics:** *\"Analyze my resume and find skill gaps\"*\n")
            content_blocks.append("- 🚀 **Freelance Marketplace:** *\"Find freelance React or Django projects\"*\n")
            content_blocks.append("- 📚 **MCQ & Entrance Prep:** *\"Show NIMCET and OJEE MCA exam syllabus and practice questions\"*\n")
            content_blocks.append("- 👥 **Recruiter Search:** *\"Find candidates skilled in Python and Django\"*\n")
            content_blocks.append("- 📊 **Platform Governance:** *\"How many active vacancies are on HireNexa?\"*\n\n")
            content_blocks.append("---\n")
            content_blocks.append("💡 *Tip: You can also configure a Google Gemini or OpenAI API key in your `.env` file (`GEMINI_API_KEY` / `OPENAI_API_KEY`) to enable unlimited multimodal generative AI.*")

        full_text = "".join(content_blocks)
        words = full_text.split(" ")
        for i in range(0, len(words), 3):
            chunk = " ".join(words[i:i+3])
            if i + 3 < len(words):
                chunk += " "
            yield chunk
            time.sleep(0.01)


# ==============================================================================
# HYBRID AI SERVICE ORCHESTRATOR
# ==============================================================================

class AIService:
    """
    Hybrid AI Orchestrator:
    - Primary: Configured external provider (OpenAI, Gemini, Groq, Anthropic)
    - Fallback: Ollama or Local Platform Intelligence
    Never exposes credentials to frontend or hides invalid credentials.
    """

    @classmethod
    def get_providers(cls) -> dict[str, BaseLLMProvider]:
        return {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
            "anthropic": AnthropicProvider(),
            "ollama": OllamaProvider(),
            "local": LocalPlatformIntelligenceProvider(),
        }

    @classmethod
    def get_status(cls) -> dict:
        providers = cls.get_providers()
        primary_pref = getattr(settings, "AI_PRIMARY_PROVIDER", "openai").lower()
        fallback_pref = getattr(settings, "AI_FALLBACK_PROVIDER", "ollama").lower()

        status_map = {}
        for name, p in providers.items():
            ok, msg = p.is_available()
            status_map[name] = {"available": ok, "message": msg, "model": p.model}

        active_provider_name = "local"
        if primary_pref in status_map and status_map[primary_pref]["available"] and primary_pref != "local":
            active_provider_name = primary_pref
        else:
            for name in ["openai", "gemini", "groq", "anthropic"]:
                if status_map[name]["available"]:
                    active_provider_name = name
                    break
            else:
                if status_map["ollama"]["available"]:
                    active_provider_name = "ollama"
                else:
                    active_provider_name = "local"

        active_p = providers[active_provider_name]
        is_external_configured = any(status_map[name]["available"] for name in ["openai", "gemini", "groq", "anthropic", "ollama"])

        return {
            "is_configured": True,
            "is_external_configured": is_external_configured,
            "primary_provider": active_provider_name,
            "primary_model": active_p.model,
            "primary_status": "configured" if active_provider_name in ["openai", "gemini", "groq", "anthropic"] else ("online" if active_provider_name == "ollama" else "platform_native"),
            "primary_message": status_map[active_provider_name]["message"],
            "fallback_provider": fallback_pref if fallback_pref in status_map else "local",
            "fallback_model": providers.get(fallback_pref, providers["local"]).model,
            "fallback_status": "online" if status_map.get(fallback_pref, {}).get("available") else "offline",
            "fallback_message": status_map.get(fallback_pref, {}).get("message", "Local Platform Intelligence available"),
            "openai_configured": status_map["openai"]["available"],
            "gemini_configured": status_map["gemini"]["available"],
            "groq_configured": status_map["groq"]["available"],
            "anthropic_configured": status_map["anthropic"]["available"],
            "ollama_online": status_map["ollama"]["available"],
            "local_ready": True,
        }

    @classmethod
    def is_configured(cls) -> bool:
        return True

    @classmethod
    def detect_and_execute_tools(cls, user_message: str, user=None) -> list[dict]:
        """Analyzes user inquiry and triggers authorized HireNexa database actions."""
        msg_lower = user_message.lower()
        executed_tools = []

        # Tool 1: Job Search
        job_keywords = ["job", "vacancy", "vacancies", "opening", "openings", "hire", "hiring", "developer", "engineer", "roles"]
        if any(k in msg_lower for k in job_keywords) and not ("status" in msg_lower and "my" in msg_lower) and not ("post" in msg_lower and "my" in msg_lower) and not ("freelance" in msg_lower or "gig" in msg_lower or "contract" in msg_lower):
            target_course = "ALL"
            if "mca" in msg_lower:
                target_course = "MCA"
            elif "mba" in msg_lower:
                target_course = "MBA"
            elif "btech" in msg_lower:
                target_course = "BTECH"

            query = ""
            for term in ["python", "django", "react", "fastapi", "devops", "cloud", "marketing", "hr", "analyst", "full stack"]:
                if term in msg_lower:
                    query = term
                    break

            loc = ""
            for city in ["bhubaneswar", "bengaluru", "bangalore", "mumbai", "delhi", "remote", "hyderabad"]:
                if city in msg_lower:
                    loc = "Remote" if city == "remote" else city.title()
                    break

            tool_res = HireNexaToolRegistry.execute_tool("search_jobs", {
                "query": query,
                "location": loc,
                "target_course": target_course,
                "limit": 5,
            }, user=user)
            if tool_res.get("success"):
                executed_tools.append(tool_res)

        # Tool 2: Freelance Projects
        freelance_keywords = ["freelance", "gig", "contract", "bounty", "project", "projects", "marketplace"]
        if any(k in msg_lower for k in freelance_keywords) and not any(t.get("tool") == "search_jobs" for t in executed_tools):
            skill = ""
            for term in ["python", "django", "react", "fastapi", "vue", "node", "ui", "ux", "design", "frontend", "backend", "full stack"]:
                if term in msg_lower:
                    skill = term
                    break
            tool_res = HireNexaToolRegistry.execute_tool("search_freelance_projects", {
                "query": skill or user_message,
                "limit": 5,
            }, user=user)
            if tool_res.get("success"):
                executed_tools.append(tool_res)

        # Tool 3: MCA Entrance Preparation & Learning
        prep_keywords = ["mca", "ojee", "nimcet", "cuet", "entrance", "mock test", "practice question", "syllabus", "exam prep", "dbms", "operating system", "computer networks", "discrete math"]
        if any(k in msg_lower for k in prep_keywords):
            tool_res = HireNexaToolRegistry.execute_tool("get_mca_prep_info", {
                "target_exam_or_topic": user_message,
            }, user=user)
            if tool_res.get("success"):
                executed_tools.append(tool_res)

        # Tool 4: My Applications (Candidate only)
        if any(phrase in msg_lower for phrase in ["my application", "application status", "applied jobs", "am i hired", "my interview"]):
            if user and user.is_authenticated:
                tool_res = HireNexaToolRegistry.execute_tool("get_my_applications", {}, user=user)
                if tool_res.get("success"):
                    executed_tools.append(tool_res)

        # Tool 5: Resume Analysis / Skill Gaps
        if any(phrase in msg_lower for phrase in ["analyze my resume", "check my resume", "review my resume", "resume score", "skill gap"]):
            if user and user.is_authenticated:
                tool_res = HireNexaToolRegistry.execute_tool("analyze_candidate_resume", {"target_role_or_job_id": user_message}, user=user)
                if tool_res.get("success"):
                    executed_tools.append(tool_res)

        # Tool 6: Talent / Candidate Search (Recruiters, Admins, Owners)
        candidate_keywords = ["find candidate", "search candidate", "talent search", "search talent", "find developer", "find applicant", "candidates skilled"]
        if any(k in msg_lower for k in candidate_keywords):
            if user and user.is_authenticated and (getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False) or getattr(user, "is_owner", False) or user.is_superuser):
                skill = ""
                for term in ["python", "django", "react", "fastapi", "sql", "java", "c++", "aws"]:
                    if term in msg_lower:
                        skill = term
                        break
                tool_res = HireNexaToolRegistry.execute_tool("search_candidates", {
                    "skill": skill,
                    "limit": 5,
                }, user=user)
                if tool_res.get("success") and tool_res.get("count", 0) > 0:
                    executed_tools.append(tool_res)

        # Tool 7: Recruiter posted jobs
        if any(phrase in msg_lower for phrase in ["jobs i posted", "my job postings", "vacancies posted", "recruiter dashboard", "hiring funnel"]):
            if user and user.is_authenticated and (getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False) or getattr(user, "is_owner", False)):
                tool_res = HireNexaToolRegistry.execute_tool("get_my_posted_jobs", {}, user=user)
                if tool_res.get("success"):
                    executed_tools.append(tool_res)

        # Tool 8: Platform Governance & Real Statistics
        admin_keywords = ["active jobs are on hirenexa", "platform stats", "platform analytics", "how many jobs", "how many active", "governance summary", "platform headcount", "platform revenue", "system health"]
        if any(k in msg_lower for k in admin_keywords):
            if user and user.is_authenticated and (getattr(user, "is_owner", False) or user.is_superuser):
                tool_res = HireNexaToolRegistry.execute_tool("get_admin_governance_summary", {}, user=user)
                if tool_res.get("success"):
                    executed_tools.append(tool_res)

        # Tool 9: Search Companies
        if any(phrase in msg_lower for phrase in ["company", "companies", "organizations", "employers"]):
            if not any(t.get("tool") in ["search_jobs", "search_freelance_projects"] for t in executed_tools):
                tool_res = HireNexaToolRegistry.execute_tool("search_companies", {"query": user_message}, user=user)
                if tool_res.get("success") and tool_res.get("count", 0) > 0:
                    executed_tools.append(tool_res)

        # Tool 10: Interview Schedule
        if any(phrase in msg_lower for phrase in ["my interview", "interview schedule", "upcoming interview", "meeting link"]):
            if user and user.is_authenticated:
                tool_res = HireNexaToolRegistry.execute_tool("get_interview_schedule", {}, user=user)
                if tool_res.get("success"):
                    executed_tools.append(tool_res)

        return executed_tools

    @classmethod
    def generate_response_stream(
        cls,
        conversation_history: list[dict],
        user_message: str,
        user=None,
        mode: str = "GENERAL",
        language: str = "en",
        image_attachment: dict | None = None,
        document_text: str = "",
        enable_web_research: bool = False,
    ) -> Generator[str, None, None]:
        providers = cls.get_providers()

        # Step 1: Execute authorized platform tools
        executed_tools = cls.detect_and_execute_tools(user_message, user=user)
        for t in executed_tools:
            yield f"data: {json.dumps({'type': 'tool', 'data': t})}\n\n"

        # Step 2: Web Research if enabled
        citations = []
        if enable_web_research:
            try:
                citations = WebResearchService.search(user_message, max_results=3)
                if citations:
                    yield f"data: {json.dumps({'type': 'citations', 'data': citations})}\n\n"
            except Exception as e:
                logger.warning("Web research error: %s", e)

        # Step 3: Build enriched system prompt and user inquiry
        system_prompt = build_system_prompt(user=user, mode=mode, language=language)

        enhanced_prompt = user_message
        if document_text:
            enhanced_prompt = (
                f"[Uploaded Document Content (Prioritize this document)]:\n"
                f"{document_text[:8000]}\n\n"
                f"---\nUser Inquiry: {user_message}"
            )

        if executed_tools:
            enhanced_prompt += (
                f"\n\n[HireNexa Platform Database Tool Results]:\n"
                f"{json.dumps(executed_tools, indent=2)}\n"
                f"Present these real vacancies/records clearly to the user with actionable next steps."
            )

        if citations:
            enhanced_prompt += (
                f"\n\n[Verified Web Citations]:\n"
                f"{json.dumps(citations, indent=2)}\n"
                f"Reference these facts and URLs accurately."
            )

        # Step 4: Provider Selection with Fallback
        status_info = cls.get_status()
        active_provider_name = status_info["primary_provider"]

        candidates = []
        if active_provider_name in providers and active_provider_name != "local":
            candidates.append(providers[active_provider_name])

        fallback_name = getattr(settings, "AI_FALLBACK_PROVIDER", "ollama").lower()
        if fallback_name in providers and fallback_name not in [p.name for p in candidates] and fallback_name != "local":
            candidates.append(providers[fallback_name])

        # Always append local platform provider as reliable last resort
        candidates.append(providers["local"])

        start_time = time.time()
        total_tokens = 0

        for idx, provider in enumerate(candidates):
            try:
                is_avail, avail_reason = provider.is_available()
                if not is_avail and provider.name != "local":
                    continue

                if idx > 0 and provider.name != "local":
                    yield f"data: {json.dumps({'type': 'provider_fallback', 'data': f'Switching to {provider.name.upper()} ({provider.model})...'})}\n\n"
                else:
                    disp_label = "HireNexa Platform Intelligence" if provider.name == "local" else f"{provider.name.upper()} ({provider.model})"
                    yield f"data: {json.dumps({'type': 'provider', 'data': disp_label})}\n\n"

                stream = provider.generate_stream(
                    system_prompt=system_prompt,
                    history=conversation_history,
                    user_prompt=enhanced_prompt,
                    image_attachment=image_attachment,
                )

                for token in stream:
                    total_tokens += 1
                    yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

                yield f"data: {json.dumps({'type': 'done', 'tokens': total_tokens, 'latency_ms': int((time.time() - start_time) * 1000), 'provider': provider.name, 'model': provider.model})}\n\n"
                return

            except AuthenticationError as auth_err:
                logger.error("Authentication error on provider %s: %s", provider.name, auth_err)
                yield f"data: {json.dumps({'type': 'error', 'data': str(auth_err)})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'tokens': 0})}\n\n"
                return

            except BadRequestError as bad_err:
                logger.error("Bad request error on provider %s: %s", provider.name, bad_err)
                yield f"data: {json.dumps({'type': 'error', 'data': str(bad_err)})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'tokens': 0})}\n\n"
                return

            except (TemporaryProviderError, OllamaUnavailableError) as temp_err:
                logger.warning("Provider %s temporary error: %s. Attempting fallback...", provider.name, temp_err)
                yield f"data: {json.dumps({'type': 'provider_fallback', 'data': f'{provider.name.upper()} temporary issue ({temp_err}). Trying fallback...'})}\n\n"
                continue

            except Exception as e:
                logger.error("Unexpected error on provider %s: %s", provider.name, e)
                continue

