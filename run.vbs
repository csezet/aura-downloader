Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = scriptDir

pythonExe = "pythonw.exe"
venvPython = scriptDir & "\venv\Scripts\pythonw.exe"
dotVenvPython = scriptDir & "\.venv\Scripts\pythonw.exe"

If fso.FileExists(venvPython) Then
    pythonExe = venvPython
ElseIf fso.FileExists(dotVenvPython) Then
    pythonExe = dotVenvPython
End If

cmd = """" & pythonExe & """ """ & scriptDir & "\main.pyw"""
WshShell.Run cmd, 1, False
