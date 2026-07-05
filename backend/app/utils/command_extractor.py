"""
Command extraction utilities for parsing terminal logs.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


class Command:
    """Represents an extracted command from terminal content."""
    
    def __init__(
        self,
        command: str,
        base_command: str,
        arguments: List[str],
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
        line_number: Optional[int] = None,
        context: Optional[str] = None
    ):
        self.command = command  # Full command line
        self.base_command = base_command  # Just the command name (e.g., "nmap")
        self.arguments = arguments  # List of arguments/flags
        self.timestamp = timestamp
        self.session_id = session_id
        self.line_number = line_number
        self.context = context  # Surrounding lines for context
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "command": self.command,
            "base_command": self.base_command,
            "arguments": self.arguments,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "session_id": self.session_id,
            "line_number": self.line_number,
            "context": self.context
        }


def extract_commands(terminal_content: str, session_id: Optional[str] = None) -> List[Command]:
    """
    Extract commands from terminal content.
    
    Supports various terminal formats:
    - Shell prompts (bash, zsh, etc.)
    - Command lines starting with $, #, >
    - Lines that look like commands (start with common command names)
    
    Args:
        terminal_content: Raw terminal log content
        session_id: Optional session ID for tracking
        
    Returns:
        List of Command objects
    """
    commands = []
    lines = terminal_content.split('\n')
    
    # Common shell prompt patterns
    prompt_patterns = [
        r'^\$',  # $ command
        r'^#',   # # root command
        r'^>',   # > continuation or prompt
        r'^\[.*\]\$',  # [user@host]$ 
        r'^\[.*\]#',   # [user@host]#
        r'^.*@.*:\$',  # user@host:$
        r'^.*@.*:#',   # user@host:#
        r'^└─\$',  # └─$ (box drawing prompt)
        r'^└─#',   # └─# (box drawing root prompt)
        r'^└─.*\$',  # └─...$ (box drawing with prompt)
        r'^└─.*#',   # └─...# (box drawing with root prompt)
        r'^msf\d+\s*>',  # msf6 > (Metasploit prompt)
        r'^.*>\s*',  # Any > prompt
    ]
    
    # Pattern for box drawing prompt lines (like ┌──(user@host)-[path])
    box_drawing_prompt_pattern = re.compile(r'^┌──.*└─[\$#]')
    
    # Common command patterns (commands that typically start lines)
    command_start_pattern = re.compile(
        r'^[a-zA-Z][a-zA-Z0-9_-]*',  # Starts with letter, followed by alphanumeric/underscore/dash
        re.IGNORECASE
    )
    
    # Common command names to identify command lines
    common_commands = {
        'nmap', 'ping', 'curl', 'wget', 'ssh', 'scp', 'rsync', 'grep', 'find',
        'ls', 'cd', 'cat', 'less', 'more', 'head', 'tail', 'grep', 'awk', 'sed',
        'python', 'python3', 'pip', 'npm', 'node', 'git', 'docker', 'kubectl',
        'msfconsole', 'metasploit', 'sqlmap', 'burpsuite', 'wireshark', 'tcpdump',
        'netstat', 'ss', 'iptables', 'firewall-cmd', 'systemctl', 'service',
        'ps', 'top', 'htop', 'kill', 'killall', 'pkill', 'pgrep',
        'tar', 'zip', 'unzip', 'gzip', 'gunzip', 'bzip2',
        'chmod', 'chown', 'sudo', 'su', 'whoami', 'id', 'groups',
        'ifconfig', 'ip', 'route', 'arp', 'nslookup', 'dig', 'host',
        'nc', 'netcat', 'telnet', 'ftp', 'sftp', 'scp',
        'vim', 'vi', 'nano', 'emacs', 'nano',
        'echo', 'printf', 'printenv', 'export', 'set', 'unset',
        'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'ln', 'touch',
        'chmod', 'chown', 'chgrp', 'umask',
        'df', 'du', 'mount', 'umount', 'fdisk', 'parted',
        'crontab', 'at', 'systemd-run',
        'history', 'which', 'whereis', 'locate', 'updatedb',
        'nikto', 'gobuster', 'strings', 'date', 'mysql',
        'use', 'set', 'exploit', 'run', 'show', 'search', 'info', 'back', 'exit',
    }
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Skip lines that are clearly not commands
        # Lines that are too long are probably output
        if len(line) > 300:
            i += 1
            continue
        
        # Lines with only special characters or numbers are probably not commands
        if re.match(r'^[^a-zA-Z]+$', line):
            i += 1
            continue
        
        # Lines that look like file paths or URLs (start with /, http, etc.)
        if re.match(r'^(/|http://|https://|ftp://)', line):
            i += 1
            continue
        
        # Check for box drawing prompt format: ┌──(user@host)-[path] followed by └─$ command
        # This is a two-line format where the prompt is on one line and command on next
        is_box_drawing_prompt = False
        command_line = None
        
        # Check if current line is a box drawing prompt line (┌──... or similar)
        # Match various box drawing characters: ┌, ├, └, ─, etc.
        if re.match(r'^[┌├└│─].*', line) or line.startswith('┌') or '──' in line[:5]:
            # Check if next line has the command with └─$ or └─# or similar
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Match box drawing prompt patterns: └─$, └─#, └─ $, etc.
                if re.match(r'^[└├│].*[\$#]', next_line) or re.match(r'^└─[\$#]', next_line) or re.match(r'^└─\s*[\$#]', next_line):
                    # Extract command from next line - remove box drawing prompt
                    command_line = re.sub(r'^[└├│].*?[\$#]\s*', '', next_line).strip()
                    command_line = re.sub(r'^└─[\$#]\s*', '', command_line).strip()
                    command_line = re.sub(r'^└─\s*[\$#]\s*', '', command_line).strip()
                    if command_line:  # Only proceed if we extracted a command
                        is_box_drawing_prompt = True
                        # Skip the prompt line and process the command line
                        i += 1
                        line = next_line
                    else:
                        # Couldn't extract command, just skip the prompt line
                        i += 1
                        continue
                else:
                    # Just a box drawing line without a command, skip it
                    i += 1
                    continue
            else:
                # Just a box drawing line at end of file, skip it
                i += 1
                continue
        
        # Check if line starts with a prompt (standard format)
        # For box drawing prompts, we still check if the line itself matches a prompt pattern
        is_prompt_line = any(re.match(pattern, line) for pattern in prompt_patterns)
        
        # Extract potential command (remove prompt if present)
        if not command_line:
            command_line = line
            if is_prompt_line:
                # Try multiple patterns to remove prompts
                # Remove Metasploit prompts first (msf6 >)
                command_line = re.sub(r'^msf\d+\s*>\s*', '', line).strip()
                # Remove box drawing prompts like └─$ or └─# (do this before other patterns)
                command_line = re.sub(r'^└─[\$#]\s*', '', command_line).strip()
                # Remove standard prompts
                command_line = re.sub(r'^[^\$#>\]]*[\$#>]\s*', '', command_line).strip()
                # Also try patterns like user@host:$
                command_line = re.sub(r'^[^:]*:\s*', '', command_line).strip()
                # Remove brackets like [user@host]$
                command_line = re.sub(r'^\[.*?\]\s*[\$#]\s*', '', command_line).strip()
                # Remove any remaining > prompts
                command_line = re.sub(r'^.*>\s*', '', command_line).strip()
        
        if not command_line:
            i += 1
            continue
        
        # Check if line looks like a command
        command_match = command_start_pattern.match(command_line)
        potential_command = None
        
        if command_match:
            potential_command = command_match.group(0).lower()
        
        # Determine if this is a command line
        is_command = False
        
        # Strategy 1: If it has a prompt (including box drawing), it's likely a command
        if (is_prompt_line or is_box_drawing_prompt) and potential_command:
            is_command = True
        # Strategy 2: If it starts with a known command (with or without args)
        elif potential_command and potential_command in common_commands:
            is_command = True
        # Strategy 3: If it looks like a command (has arguments, reasonable length)
        elif potential_command and len(command_line.split()) > 1:
            # Additional check: command should be reasonable length (not too long)
            if len(potential_command) <= 25 and len(command_line) < 250:
                # Check if it's not just a path or URL
                if not re.match(r'^(/|\./|\.\./|http://|https://)', command_line):
                    # Check if it looks like a command (has alphanumeric start, reasonable structure)
                    if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*(\s+[^\s]+)*$', command_line):
                        is_command = True
        
        # Additional filters to reduce false positives
        if is_command:
            # Don't treat lines that are mostly numbers/special chars as commands
            if len(re.sub(r'[a-zA-Z]', '', command_line)) > len(command_line) * 0.7:
                is_command = False
            
            # Don't treat lines that look like file listings as commands
            if re.match(r'^[drwx-]{10}\s+', command_line):
                is_command = False
            
            # Don't treat lines that are just numbers as commands
            if re.match(r'^\d+$', command_line):
                is_command = False
        
        if is_command:
            # command_line already extracted above, just need to clean it up
            # Remove any remaining prompt artifacts
            if is_prompt_line or is_box_drawing_prompt:
                # Additional cleanup for edge cases
                # Remove Metasploit prompts first (msf6 >)
                command_line = re.sub(r'^msf\d+\s*>\s*', '', command_line).strip()
                # Remove standard prompts
                command_line = re.sub(r'^[^\$#>\]]*[\$#>]\s*', '', command_line).strip()
                command_line = re.sub(r'^\[.*?\]\s*[\$#]\s*', '', command_line).strip()
                # Remove box drawing prompts
                command_line = re.sub(r'^└─[\$#]\s*', '', command_line).strip()
                # Remove any remaining > prompts
                command_line = re.sub(r'^.*>\s*', '', command_line).strip()
            
            # Parse command and arguments
            # For commands with && or ||, we want to keep the full command but extract the first base command
            # Use simple split to preserve && and || operators
            parts = command_line.split() if command_line else []
            
            if parts:
                # Find the first actual command (skip operators like &&, ||, ;)
                base_cmd = None
                args = []
                for part in parts:
                    if part not in ['&&', '||', ';', '|'] and not base_cmd:
                        base_cmd = part
                    elif base_cmd:
                        args.append(part)
                
                # If no base command found, use first part
                if not base_cmd and parts:
                    base_cmd = parts[0]
                    args = parts[1:] if len(parts) > 1 else []
                
                # Get context (previous and next few lines)
                context_lines = []
                start_ctx = max(0, i - 2)
                end_ctx = min(len(lines), i + 3)
                context_lines = lines[start_ctx:end_ctx]
                context = '\n'.join(context_lines)
                
                command = Command(
                    command=command_line,
                    base_command=base_cmd,
                    arguments=args,
                    session_id=session_id,
                    line_number=i + 1,
                    context=context
                )
                commands.append(command)
        
        i += 1
    
    return commands


def analyze_command_frequency(commands: List[Command]) -> Dict[str, int]:
    """
    Analyze command frequency.
    
    Args:
        commands: List of Command objects
        
    Returns:
        Dictionary mapping command names to usage counts
    """
    counter = Counter()
    for cmd in commands:
        counter[cmd.base_command] += 1
    return dict(counter)


def detect_command_patterns(commands: List[Command], min_sequence_length: int = 2) -> List[Dict]:
    """
    Detect common command patterns/sequences.
    
    Args:
        commands: List of Command objects
        min_sequence_length: Minimum length of sequence to detect
        
    Returns:
        List of pattern dictionaries with sequence and frequency
    """
    if len(commands) < min_sequence_length:
        return []
    
    # Build sequences
    sequences = defaultdict(int)
    
    # Look for sequences of consecutive commands
    for i in range(len(commands) - min_sequence_length + 1):
        sequence = tuple(cmd.base_command for cmd in commands[i:i + min_sequence_length])
        sequences[sequence] += 1
    
    # Filter sequences that appear multiple times
    patterns = []
    for sequence, count in sequences.items():
        if count >= 2:  # Only patterns that appear at least twice
            patterns.append({
                "sequence": list(sequence),
                "frequency": count,
                "length": len(sequence)
            })
    
    # Sort by frequency (descending)
    patterns.sort(key=lambda x: x["frequency"], reverse=True)
    
    return patterns


def build_command_timeline(commands: List[Command]) -> List[Dict]:
    """
    Build timeline data for commands.
    
    Args:
        commands: List of Command objects
        
    Returns:
        List of timeline entries
    """
    timeline = []
    
    for cmd in commands:
        entry = {
            "command": cmd.base_command,
            "full_command": cmd.command,
            "timestamp": cmd.timestamp.isoformat() if cmd.timestamp else None,
            "session_id": cmd.session_id,
            "line_number": cmd.line_number
        }
        timeline.append(entry)
    
    # Sort by timestamp or line number
    timeline.sort(key=lambda x: x["timestamp"] if x["timestamp"] else f"line_{x['line_number']}")
    
    return timeline



