"""OpenAI LLM Provider implementation.

This module implements the LLM provider interface for OpenAI's API,
supporting models like GPT-4o and GPT-5.
"""

import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import openai
from dotenv import load_dotenv

from app.ai_agent.providers.base import LLMProvider
from app.ai_agent.utils.token_utils import count_tokens
from common.logger import logger


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation.
    
    This provider uses the OpenAI API for chat completions and supports
    native token counting via tiktoken.
    
    Supported models: gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o, gpt-5 variants
    """
    
    # Supported OpenAI models
    SUPPORTED_MODELS = {
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-3.5-turbo",
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4-turbo-preview",
        "gpt-3.5-turbo-16k",
    }
    
    def __init__(self):
        """Initialize the OpenAI provider.
        
        Loads API key from environment and configures the OpenAI client.
        
        Raises:
            ValueError: If OPENAI_API_KEY is not found in environment.
        """
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        openai.api_key = api_key
        self._api_key = api_key
        self._client = openai.OpenAI(api_key=api_key)
        self._default_model = os.getenv("LLM_MODEL", "gpt-5")
        logger.info(f"OpenAI provider initialized with model: {self._default_model}")
    
    @property
    def name(self) -> str:
        """Return provider name."""
        return "openai"
    
    @property
    def default_model(self) -> str:
        """Return default model name."""
        return self._default_model
    
    @property
    def supports_native_token_counting(self) -> bool:
        """OpenAI supports native token counting via tiktoken."""
        return True
    
    def chat_completion(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        input_text: Optional[str] = None,
        prompt_cache_key: Optional[str] = None,
        prompt_cache_retention: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """Send a chat completion request to OpenAI.
        
        Args:
            messages: Optional list of message dicts.
            model: Optional model name. If None, uses default_model.
            instructions: Optional instructions for Responses API.
            input_text: Optional input text for Responses API.
            prompt_cache_key: Optional prompt cache key.
            prompt_cache_retention: Optional prompt cache retention time.
            max_output_tokens: Optional max output tokens.
        
        Returns:
            The AI's response text.
        """
        model_to_use = model or self._default_model
        
        if not self.validate_model(model_to_use):
            raise ValueError(f"Model '{model_to_use}' is not supported by OpenAI provider")
        
        if instructions is not None and input_text is not None:
            # Use Responses API
            request_kwargs: dict[str, Any] = {
                "model": model_to_use,
                "instructions": instructions,
                "input": input_text,
                "temperature": 0,
            }
            if max_output_tokens is not None:
                request_kwargs["max_output_tokens"] = max_output_tokens
            if prompt_cache_key:
                request_kwargs["prompt_cache_key"] = prompt_cache_key
            if prompt_cache_retention:
                request_kwargs["prompt_cache_retention"] = prompt_cache_retention

            try:
                logger.debug(
                    "Sending Responses API request to OpenAI model: %s (input chars=%s)",
                    model_to_use,
                    len(input_text),
                )
                response = self._client.responses.create(**request_kwargs)
                response_text = self._extract_response_text(response)
                usage = getattr(response, "usage", None)
                cached_tokens = None
                if usage is not None:
                    prompt_details = getattr(usage, "input_tokens_details", None) or getattr(
                        usage, "prompt_tokens_details", None
                    )
                    if prompt_details is not None:
                        cached_tokens = getattr(prompt_details, "cached_tokens", None)
                logger.debug(
                    "Received Responses API result: output_chars=%s cached_tokens=%s",
                    len(response_text),
                    cached_tokens,
                )
                return response_text
            except Exception as e:
                logger.error(f"OpenAI Responses API error: {e}")
                raise RuntimeError(f"OpenAI Responses API error: {e}") from e
        else:
            # Use Standard Chat Completions API
            if not messages:
                raise ValueError("messages must be provided if not using instructions/input_text")
                
            try:
                logger.debug(f"Sending {len(messages)} messages to OpenAI model: {model_to_use}")
                response = openai.chat.completions.create(
                    model=model_to_use,
                    messages=messages
                )
                ai_message = response.choices[0].message.content.strip()
                logger.debug(f"Received response from OpenAI: {len(ai_message)} characters")
                return ai_message
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
                raise RuntimeError(f"OpenAI error: {e}") from e

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract aggregated text from a Responses API result."""
        output_text = getattr(response, "output_text", "")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) != "output_text":
                    continue
                text = getattr(content, "text", None)
                if text:
                    chunks.append(text)
        return "".join(chunks).strip()

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a tool-enabled chat completion request to OpenAI.

        Args:
            messages: List of chat messages.
            tools: OpenAI function/tool definitions.
            model: Optional model name. If None, uses default_model.

        Returns:
            Structured response with assistant content, requested tool calls,
            and finish reason.
        """
        model_to_use = model or self._default_model

        if not self.validate_model(model_to_use):
            raise ValueError(f"Model '{model_to_use}' is not supported by OpenAI provider")

        try:
            logger.debug(
                "Sending %s messages and %s tools to OpenAI model: %s",
                len(messages),
                len(tools),
                model_to_use,
            )
            response = openai.chat.completions.create(
                model=model_to_use,
                messages=messages,
                tools=tools,
            )

            message = response.choices[0].message
            content = (message.content or "").strip()

            tool_calls = []
            for tool_call in message.tool_calls or []:
                raw_args = tool_call.function.arguments or "{}"
                try:
                    parsed_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}

                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": parsed_args,
                    }
                )

            return {
                "content": content,
                "tool_calls": tool_calls,
                "finish_reason": response.choices[0].finish_reason,
            }
        except Exception as e:
            logger.error(f"OpenAI API tool-calling error: {e}")
            raise RuntimeError(f"OpenAI tool-calling error: {e}") from e
    
    def count_tokens(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> int:
        """Count tokens using tiktoken.
        
        Args:
            messages: List of message dicts.
            model: Optional model name for model-specific encoding.
        
        Returns:
            Accurate token count via tiktoken.
        """
        model_to_use = model or self._default_model
        return count_tokens(messages, model_to_use)
    
    def validate_model(self, model: str) -> bool:
        """Validate if model is supported by OpenAI provider.
        
        Args:
            model: Model name to validate.
        
        Returns:
            True if model is in SUPPORTED_MODELS set.
        """
        return model in self.SUPPORTED_MODELS

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Async generator that streams OpenAI chat completion tokens.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Optional model name. If None, uses default_model.

        Yields:
            Token strings as they arrive from the OpenAI streaming API.

        Raises:
            ValueError: If model is not supported.
            RuntimeError: If the OpenAI streaming API call fails.
        """
        model_to_use = model or self._default_model

        if not self.validate_model(model_to_use):
            raise ValueError(f"Model '{model_to_use}' is not supported by OpenAI provider")

        async_client = openai.AsyncOpenAI(api_key=self._api_key)
        try:
            logger.debug(
                "Starting streaming request to OpenAI model: %s (%s messages)",
                model_to_use,
                len(messages),
            )
            stream = await async_client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                stream=True,
                timeout=180,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("OpenAI streaming API error: %s", e)
            raise RuntimeError(f"OpenAI streaming error: {e}") from e
        finally:
            await async_client.close()
