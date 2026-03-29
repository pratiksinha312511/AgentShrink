import shutil
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path.home() / ".agentshrink" / "logs.db"
OUTPUT_DIR = PROJECT_ROOT / ".agentshrink_output"
BACKUP_ROOT = PROJECT_ROOT / ".agentshrink_backups"


def main():
    console = Console()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"finetune_lab_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    moved = []
    if DB_PATH.exists():
        db_backup = backup_dir / "logs.db"
        shutil.copy2(DB_PATH, db_backup)
        DB_PATH.unlink()
        moved.append(str(db_backup))

    if OUTPUT_DIR.exists():
        output_backup = backup_dir / ".agentshrink_output"
        if output_backup.exists():
            shutil.rmtree(output_backup)
        shutil.copytree(OUTPUT_DIR, output_backup)
        shutil.rmtree(OUTPUT_DIR)
        moved.append(str(output_backup))

    console.print(Panel.fit(
        "[bold green]Fine-tune lab state reset complete[/bold green]\n"
        f"Backup location: {backup_dir}\n"
        f"Backed up: {', '.join(moved) if moved else 'nothing (state was already clean)'}",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
