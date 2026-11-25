Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\ExplainLab\desktop"
WshShell.Run """D:\ExplainLab\desktop\node_modules\electron\dist\electron.exe"" ""D:\ExplainLab\desktop""", 1, False
