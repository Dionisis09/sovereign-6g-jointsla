$ErrorActionPreference = 'Stop'
$documentPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'JointSLA_v2_Experimental_Report.docx'))
$qaDirectory = Join-Path $PSScriptRoot 'qa'
[IO.Directory]::CreateDirectory($qaDirectory) | Out-Null
$pdfPath = Join-Path $qaDirectory 'JointSLA_v2_Experimental_Report.pdf'
$wordInstance = $null
$wordDocument = $null
try {
    $wordInstance = New-Object -ComObject Word.Application
    $wordInstance.Visible = $false
    $wordInstance.DisplayAlerts = 0
    $wordInstance.AutomationSecurity = 3
    $wordDocument = $wordInstance.Documents.Open($documentPath, $false, $false)
    $wordDocument.Fields.Update() | Out-Null
    foreach ($contents in $wordDocument.TablesOfContents) { $contents.Update() }
    $wordDocument.Repaginate()
    $wordDocument.Fields.Update() | Out-Null
    $wordDocument.Save()
    $wordDocument.ExportAsFixedFormat($pdfPath, 17)
    Write-Output ('PDF exported: ' + $pdfPath)
    Write-Output ('Pages: ' + $wordDocument.ComputeStatistics(2))
} finally {
    if ($null -ne $wordDocument) { $wordDocument.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordDocument) | Out-Null }
    if ($null -ne $wordInstance) { $wordInstance.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordInstance) | Out-Null }
}
