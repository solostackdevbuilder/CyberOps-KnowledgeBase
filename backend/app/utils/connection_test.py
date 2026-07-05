"""
Connection testing utilities for databases and LLM providers.
"""
from typing import Tuple

from app.models_settings import DatabaseConfig, LLMConfig, LLMProvider


async def test_mongodb_connection(config: DatabaseConfig) -> Tuple[bool, str]:
    """
    Test MongoDB connection.
    
    Args:
        config: MongoDB configuration
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from app.core.storage.mongodb_store import MongoDBStore
        store = MongoDBStore(config)
        success = await store.test_connection()
        if success:
            return True, "MongoDB connection successful"
        else:
            return False, "MongoDB connection failed: ping test failed"
    except ImportError as e:
        return False, f"MongoDB connection failed: motor package not installed. Install with: pip install motor"
    except Exception as e:
        return False, f"MongoDB connection failed: {str(e)}"


async def test_postgresql_connection(config: DatabaseConfig) -> Tuple[bool, str]:
    """
    Test PostgreSQL connection.
    
    Args:
        config: PostgreSQL configuration
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # PostgreSQL is not yet implemented, so just check config
        if not config.connection_string and (not config.host or not config.database_name):
            return False, "PostgreSQL connection failed: Either connection_string or (host and database_name) must be provided"
        return False, "PostgreSQL storage is not yet implemented"
    except ImportError as e:
        return False, f"PostgreSQL connection failed: asyncpg package not installed. Install with: pip install asyncpg"
    except Exception as e:
        return False, f"PostgreSQL connection failed: {str(e)}"


async def test_ollama_connection(endpoint: str) -> Tuple[bool, str]:
    """
    Test Ollama connection.
    
    Args:
        endpoint: Ollama server endpoint
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from app.core.services.ollama_service import OllamaService
        # Create a temporary service instance to test
        service = OllamaService(endpoint=endpoint, model_name="llama2")
        success = await service.test_connection()
        await service.close()
        
        if success:
            return True, f"Ollama connection successful at {endpoint}"
        else:
            return False, f"Ollama connection failed at {endpoint}"
    except ImportError as e:
        return False, f"Ollama connection failed: httpx package not installed. Install with: pip install httpx"
    except Exception as e:
        return False, f"Ollama connection failed: {str(e)}"


async def test_openai_connection(api_key: str, endpoint: str = None) -> Tuple[bool, str]:
    """
    Test OpenAI connection.
    
    Args:
        api_key: OpenAI API key
        endpoint: Optional custom endpoint URL
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from app.core.services.openai_service import OpenAIService
        service = OpenAIService(api_key=api_key, endpoint=endpoint)
        success = await service.test_connection()
        
        if success:
            endpoint_msg = f" at {endpoint}" if endpoint else ""
            return True, f"OpenAI connection successful{endpoint_msg}"
        else:
            return False, "OpenAI connection failed: API test failed"
    except ImportError as e:
        return False, f"OpenAI connection failed: openai package not installed. Install with: pip install openai"
    except Exception as e:
        return False, f"OpenAI connection failed: {str(e)}"


async def test_claude_connection(api_key: str) -> Tuple[bool, str]:
    """
    Test Claude connection.
    
    Args:
        api_key: Anthropic API key
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from app.core.services.claude_service import ClaudeService
        service = ClaudeService(api_key=api_key)
        success = await service.test_connection()
        
        if success:
            return True, "Claude connection successful"
        else:
            return False, "Claude connection failed: API test failed"
    except ImportError as e:
        return False, f"Claude connection failed: anthropic package not installed. Install with: pip install anthropic"
    except Exception as e:
        return False, f"Claude connection failed: {str(e)}"


async def test_llm_connection(llm_config: LLMConfig) -> Tuple[bool, str]:
    """
    Test LLM connection based on config.
    
    Args:
        llm_config: LLM configuration
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if llm_config.provider == LLMProvider.CLAUDE:
        if not llm_config.api_key:
            return False, "Claude API key is required"
        return await test_claude_connection(llm_config.api_key)
    elif llm_config.provider == LLMProvider.OPENAI:
        if not llm_config.api_key:
            return False, "OpenAI API key is required"
        return await test_openai_connection(llm_config.api_key, llm_config.endpoint)
    elif llm_config.provider == LLMProvider.OLLAMA:
        if not llm_config.endpoint:
            return False, "Ollama endpoint is required"
        return await test_ollama_connection(llm_config.endpoint)
    else:
        return False, f"Unsupported LLM provider: {llm_config.provider}"

