Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = scriptDir

pythonExe = "pythonw.exe"
venvPython = scriptDir & "\venv\Scripts\pythonw.exe"
hermesPython = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\hermes\hermes-agent\venv\Scripts\pythonw.exe"

If fso.FileExists(venvPython) Then
    pythonExe = venvPython
ElseIf fso.FileExists(hermesPython) Then
    pythonExe = hermesPython
End If

cmd = """" & pythonExe & """ """ & scriptDir & "\main.pyw"""
WshShell.Run cmd, 0, False
