' Launches FileNail without a console window.
Set shell = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
script = folder & "\filenail.pyw"

Function Found(cmd)
  Found = (shell.Run("cmd /c where " & cmd & " >nul 2>&1", 0, True) = 0)
End Function

If Found("pyw") Then
  shell.Run "pyw -3 """ & script & """", 0, False
ElseIf Found("pythonw") Then
  shell.Run "pythonw """ & script & """", 0, False
Else
  MsgBox "Python was not found. Install Python from python.org, then try again.", 16, "FileNail"
End If
