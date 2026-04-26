from typing import Any, Optional
import hashlib
from db.models import File, merge_file
from pathlib import Path
from common.logger import logger

def generate_file_hash(file_path: str) -> str:
    """
    Generate a hash for a file path to create unique file IDs.
    
    Args:
        file_path: Full file path
        
    Returns:
        str: 8-character hash of the file path
    """
    return hashlib.sha256(file_path.encode()).hexdigest()[:8]


def new_file_handler(
    session: Any,
    repo_name: str,
    file_path: str,
    created_at: str,
    file_size: int = 0,
    repo_owner: Optional[str] = None,
    branch: str = "main"
) -> str:
    """
    Create or update a File node in Neo4j.

    Args:
        session: Neo4j session
        repo_name: Repository name for ID generation
        file_path: Full path to the file
        created_at: Timestamp of first commit that created/modified this file
        file_size: File size in bytes (optional)
        repo_owner: GitHub repository owner (optional, for URL generation)
        branch: Git branch name (default: "main")

    Returns:
        str: File ID
    """
    try:
        logger.debug(f"        Processing file: {file_path}")
        
        # Generate file ID
        path_hash = generate_file_hash(file_path)
        file_id = f"file_{repo_name}_{path_hash}"
        logger.debug(f"        Generated file ID: {file_id} (hash: {path_hash})")

        # Extract file metadata
        path_obj = Path(file_path)
        file_name = path_obj.name
        extension = path_obj.suffix or ".txt"
        logger.debug(f"        File metadata: name='{file_name}', extension='{extension}', size={file_size}")

        # Determine language from extension
        ext_to_lang = {
            ".py": "Python", ".go": "Go", ".yaml": "YAML", ".yml": "YAML",
            ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
            ".swift": "Swift", ".java": "Java", ".c": "C", ".cpp": "C++", ".h": "C/C++",
            ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
            ".md": "Markdown", ".json": "JSON", ".sh": "Shell", ".css": "CSS",
            ".html": "HTML", ".xml": "XML", ".sql": "SQL", ".txt": "Text"
        }
        language = ext_to_lang.get(extension.lower(), "Unknown")
        logger.debug(f"        Detected language: {language}")

        # Determine if test file
        is_test = any(x in file_path.lower() for x in ["test", "spec", "__tests__", "tests/", ".test.", ".spec."])
        logger.debug(f"        Is test file: {is_test}")

        # Generate GitHub URL if owner is provided
        github_url = None
        if repo_owner:
            github_url = f"https://github.com/{repo_owner}/{repo_name}/blob/{branch}/{file_path}"
            logger.debug(f"        Generated URL: {github_url}")

        # Check if file already exists - only update created_at if new file has earlier date
        logger.debug(f"        Checking if file exists: {file_id}")
        check_query = """
        MATCH (f:File {id: $file_id})
        RETURN f.created_at as existing_created_at
        LIMIT 1
        """
        result = session.run(check_query, file_id=file_id)
        record = result.single()
        
        original_created_at = created_at
        if record:
            # File exists - keep the earlier created_at date
            existing_created_at = record["existing_created_at"]
            logger.debug(f"        File exists with created_at: {existing_created_at}")
            if existing_created_at:
                # Convert Neo4j DateTime to ISO string for comparison
                if hasattr(existing_created_at, 'isoformat'):
                    existing_created_at_str = existing_created_at.isoformat()
                else:
                    existing_created_at_str = str(existing_created_at)

                # Compare ISO strings
                if existing_created_at_str < created_at:
                    created_at = existing_created_at_str
                    logger.debug(f"        Using existing earlier created_at: {created_at}")
                else:
                    logger.debug(f"        Using new earlier created_at: {created_at}")
        else:
            logger.debug(f"        File does not exist, will create new")

        # Create File node
        logger.debug(f"        Creating File node: {file_id}")
        file = File(
            id=file_id,
            path=file_path,
            name=file_name,
            extension=extension,
            language=language,
            is_test=is_test,
            size=file_size,
            created_at=created_at,
            url=github_url
        )

        # Merge into Neo4j
        logger.debug(f"        Merging File node")
        merge_file(session, file)
        
        logger.debug(f"        File processing complete: {file_id}")
        return file_id

    except Exception as e:
        logger.debug(f"        Error creating File for {file_path}: {str(e)}", exc_info=True)
        logger.exception(e)
        # Return a fallback file ID
        fallback_id = f"file_{repo_name}_error"
        return fallback_id