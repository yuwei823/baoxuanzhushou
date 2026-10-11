"""Isolated WPS reader, invoked with the installed pywin32-enabled Python."""

import json
import sys
from pathlib import Path


def main():
    import win32com.client

    application = win32com.client.DispatchEx("kwps.application")
    try:
        application.Visible = False
        application.DisplayAlerts = 0
        application.AutomationSecurity = 3
        document = application.Documents.Open(
            str(Path(sys.argv[1]).resolve()),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        try:
            result = {
                "units": [p.Range.Text for p in document.Paragraphs],
                "tool": "WPS COM paragraphs",
                "version": str(application.Version),
            }
            Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        finally:
            document.Close(SaveChanges=0)
    finally:
        application.Quit(SaveChanges=0)


if __name__ == "__main__":
    main()
