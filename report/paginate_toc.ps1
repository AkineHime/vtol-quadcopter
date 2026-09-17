# Fill the TOC "Page No." column with real page numbers, then export PDF.
$ErrorActionPreference = "Stop"
$root = "E:\proggramming\semester proj\report"
$doc  = "$root\report.docx"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$d = $word.Documents.Open($doc)

# Repaginate
$d.Repaginate()

# List of body (non-table) paragraphs: normalized text + adjusted page number
$paras = New-Object System.Collections.ArrayList
foreach ($p in $d.Paragraphs) {
    if ($p.Range.Information(12)) { continue }   # wdWithInTable -> skip
    $t = (($p.Range.Text).Trim() -replace '\s+', ' ')
    if ($t.Length -eq 0) { continue }
    $null = $paras.Add([pscustomobject]@{
        Text = $t
        Page = $p.Range.Information(1)   # wdActiveEndAdjustedPageNumber
    })
}

function PageFor($needle) {
    $n = ($needle -replace '\s+', ' ').Trim()
    # exact / prefix first
    foreach ($x in $paras) { if ($x.Text -eq $n) { return $x.Page } }
    foreach ($x in $paras) { if ($x.Text -like "$n*") { return $x.Page } }
    # then "heading ends with this label" (number lives in TOC col 1)
    foreach ($x in $paras) {
        if ($x.Text.Length -lt 90 -and $x.Text -like "*$n") { return $x.Page }
    }
    # last resort: any paragraph starting with the label (e.g. long 4.2.3 line)
    foreach ($x in $paras) { if ($x.Text -like "$n*") { return $x.Page } }
    return $null
}

# The TOC table is the one whose first cell says "Sl.No"
foreach ($tbl in $d.Tables) {
    $h = ($tbl.Cell(1,1).Range.Text -replace '[\r\a]','').Trim()
    if ($h -ne "Sl.No") { continue }
    for ($r = 2; $r -le $tbl.Rows.Count; $r++) {
        $label = ($tbl.Cell($r,2).Range.Text -replace '[\r\a]','').Trim()
        $slno  = ($tbl.Cell($r,1).Range.Text -replace '[\r\a]','').Trim()
        if ($label.Length -eq 0) { continue }
        $needle = ($label -replace '\s*<.*$','').Trim()
        $pg = $null
        if ($needle -match '^Abstract') {
            $pg = "i"
        } else {
            if ($slno -match '^\d') { $needle = "$slno $needle" }
            $pg = PageFor $needle
        }
        if ($null -ne $pg) {
            $cell = $tbl.Cell($r,3)
            $cell.Range.Text = [string]$pg
        }
    }
}

$d.Repaginate()
$d.Save()
$d.SaveAs([ref]"$root\report.pdf", [ref]17)
$pages = $d.ComputeStatistics(2)
$d.Close()
$word.Quit()
Write-Output "pages=$pages"
Write-Output "done"
