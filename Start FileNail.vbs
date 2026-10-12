' Launches FileNail without a console window.
' If Python is missing, downloads the official Python 3.15 installer from python.org.
Set shell = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
script = folder & "\filenail.pyw"
q = Chr(34)

pythonw = FindPythonW()
If pythonw = "" Then
  answer = MsgBox("FileNail needs Python, and this PC does not have it yet." & vbCrLf & vbCrLf & "Download and install Python 3.15 from python.org? This can take a few minutes. Python stays on this PC afterwards.", vbYesNo + vbQuestion, "FileNail")
  If answer <> vbYes Then
    WScript.Quit 0
  End If
  pythonw = InstallPython()
End If

If pythonw = "" Then
  MsgBox "FileNail could not install Python. Check the internet connection, or install Python from python.org, then try again.", vbCritical, "FileNail"
  WScript.Quit 1
End If

shell.Run q & pythonw & q & " " & q & script & q, 0, False

Function FindPythonW()
  Dim local, programs, tags, i, path
  FindPythonW = ""
  local = shell.ExpandEnvironmentStrings("%LocalAppData%")
  programs = shell.ExpandEnvironmentStrings("%ProgramFiles%")
  tags = Array("315", "314", "313", "312", "311", "310")
  For i = 0 To UBound(tags)
    path = FirstReal(Array( _
      local & "\Programs\Python\Python" & tags(i) & "\pythonw.exe", _
      local & "\Programs\Python\Python" & tags(i) & "-64\pythonw.exe", _
      local & "\Programs\Python\Python" & tags(i) & "-32\pythonw.exe", _
      programs & "\Python" & tags(i) & "\pythonw.exe", _
      programs & "\Python" & tags(i) & "-32\pythonw.exe" _
    ))
    If path <> "" Then
      FindPythonW = path
      Exit Function
    End If
  Next
  path = WhereExe("pythonw")
  If path <> "" Then
    FindPythonW = path
    Exit Function
  End If
  FindPythonW = WhereExe("pyw")
End Function

Function FirstReal(paths)
  Dim i
  FirstReal = ""
  For i = 0 To UBound(paths)
    If RealExe(paths(i)) Then
      FirstReal = paths(i)
      Exit Function
    End If
  Next
End Function

Function RealExe(path)
  RealExe = False
  If path = "" Then Exit Function
  If InStr(1, path, "\WindowsApps\", 1) > 0 Then Exit Function
  If fso.FileExists(path) Then RealExe = True
End Function

Function WhereExe(cmd)
  Dim exec, waited, line
  WhereExe = ""
  On Error Resume Next
  Set exec = shell.Exec("cmd /c where " & cmd)
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  On Error GoTo 0
  waited = 0
  Do While exec.Status = 0 And waited < 50
    WScript.Sleep 100
    waited = waited + 1
  Loop
  Do Until exec.StdOut.AtEndOfStream
    line = Trim(exec.StdOut.ReadLine())
    If RealExe(line) Then
      WhereExe = line
      Exit Function
    End If
  Loop
End Function

Function CpuArch()
  Dim native
  CpuArch = UCase(shell.ExpandEnvironmentStrings("%PROCESSOR_ARCHITECTURE%"))
  native = shell.ExpandEnvironmentStrings("%PROCESSOR_ARCHITEW6432%")
  If native <> "" And native <> "%PROCESSOR_ARCHITEW6432%" Then
    CpuArch = UCase(native)
  End If
End Function

Function InstallPython()
  Dim arch, suffix, tag, url, temp, installer, target, log, code
  InstallPython = ""
  arch = CpuArch()
  If arch = "ARM64" Then
    suffix = "-arm64.exe"
  ElseIf arch = "AMD64" Then
    suffix = "-amd64.exe"
  Else
    suffix = ".exe"
  End If
  tag = "Python315"
  If arch <> "AMD64" And arch <> "ARM64" Then tag = "Python315-32"
  url = "https://www.python.org/ftp/python/3.15.0/python-3.15.0" & suffix
  temp = shell.ExpandEnvironmentStrings("%TEMP%")
  installer = temp & "\FileNail-python-3.15.0" & suffix
  target = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\" & tag
  log = temp & "\FileNail-python-install.log"
  If Not Download(url, installer) Then Exit Function
  code = shell.Run(q & installer & q & " /passive InstallAllUsers=0 Include_launcher=0 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Shortcuts=0 Include_tcltk=1 PrependPath=1 TargetDir=" & q & target & q & " /log " & q & log & q, 1, True)
  If code <> 0 And code <> 3010 Then Exit Function
  If RealExe(target & "\pythonw.exe") Then
    InstallPython = target & "\pythonw.exe"
    Exit Function
  End If
  InstallPython = FindPythonW()
End Function

Function Download(url, dest)
  Dim code
  Download = False
  On Error Resume Next
  If fso.FileExists(dest) Then fso.DeleteFile dest, True
  On Error GoTo 0
  shell.Environment("PROCESS")("FILENAIL_URL") = url
  shell.Environment("PROCESS")("FILENAIL_DEST") = dest
  code = shell.Run("cmd /c title FileNail && echo Downloading Python from python.org... && curl.exe -L --fail --retry 3 -o ""%FILENAIL_DEST%"" ""%FILENAIL_URL%""", 1, True)
  If code <> 0 Then
    code = shell.Run("powershell -NoProfile -Command ""[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri $env:FILENAIL_URL -OutFile $env:FILENAIL_DEST""", 0, True)
  End If
  If code <> 0 Then Exit Function
  If Not fso.FileExists(dest) Then Exit Function
  If fso.GetFile(dest).Size < 8000000 Then Exit Function
  Download = True
End Function
