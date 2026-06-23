Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Projects-D\s2connects AI Voice bot\scaiva\ui"
WshShell.Run "cmd.exe /c ""C:\Program Files\Volta\pnpm.exe"" run dev > ..\logs\latest\ui_vbs.log 2>&1", 0, False
