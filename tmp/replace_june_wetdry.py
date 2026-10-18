from pathlib import Path
import csv,json
import numpy as np
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from pypdf import PdfReader,PdfWriter
import pdfplumber
root=Path('/Users/isoto/Projects/Rainfall-Estimation'); pipe=root/'Compute-Link-Attenuations/June2023HundredPatches/pipeline'
methods=[('IDW','sol_dir_idw'),('ILDW','sol_dir_ildw'),('Solver(ILDW) light shrinkage','sol_dir_solver_ildw_timing'),('Solver(ILDW) no shrinkage','sol_dir_solver_ildw_no_shrinkage'),('Convex Solver light shrinkage','sol_dir_convex_light_shrinkage'),('Convex Solver no shrinkage','sol_dir_convex_no_shrinkage'),('Homotopy Solver light shrinkage','sol_dir_homotopy_light_shrinkage'),('Homotopy Solver no shrinkage','sol_dir_homotopy_no_shrinkage'),('ILDW-init Roy DCT','sol_dir_roy_dct_ildw_outer50')]
gts=sorted((pipe.parent/'gt_dir').glob('gt_*.npz'));assert len(gts)==100
results=[]; perpatch=[]
for label,directory in methods:
 values=[]
 for gp in gts:
  sp=pipe/'solutions'/directory/f'est_input_{gp.stem[3:]}_solution.npz'
  with np.load(gp) as z:gt=z['R_gt']
  with np.load(sp) as z:pred=z['R_hat']
  assert gt.shape==pred.shape
  mask=np.isfinite(gt)&np.isfinite(pred);assert mask.all()
  wet=gt[mask]>=.6;pw=pred[mask]>=.6
  tp=int(np.count_nonzero(wet&pw));fp=int(np.count_nonzero(~wet&pw));tn=int(np.count_nonzero(~wet&~pw));fn=int(np.count_nonzero(wet&~pw))
  n=wet.size;nw=int(wet.sum());nd=n-nw;assert tp+fp+tn+fn==n
  fractions=np.array([tp,fp,tn,fn])/n
  rates=np.array([tp/nw if nw else np.nan,fp/nd if nd else np.nan,tn/nd if nd else np.nan,fn/nw if nw else np.nan])
  assert abs(fractions.sum()-1)<1e-12
  if nw:assert abs(rates[0]+rates[3]-1)<1e-12
  if nd:assert abs(rates[1]+rates[2]-1)<1e-12
  values.append(np.r_[fractions,rates]);perpatch.append(dict(method=label,patch=gp.stem[3:],pixels=n,wet_gt=nw,dry_gt=nd,true_wet=tp,false_wet=fp,true_dry=tn,false_dry=fn))
 arr=np.array(values);summary=np.nanmean(arr,axis=0)
 results.append(dict(method=label,n_patches=len(values),fraction=summary[:4].tolist(),conditional=summary[4:].tolist(),conditional_patch_counts=np.isfinite(arr[:,4:]).sum(axis=0).tolist()))
 print(label,np.round(summary,3),flush=True)
styles=getSampleStyleSheet();cell=ParagraphStyle('Cell',fontName='Times-Roman',fontSize=8,leading=10);head=ParagraphStyle('Head',fontName='Helvetica',fontSize=8,leading=10)
rows=[['Method','Fraction of all pixels','','','','Conditional rate','','',''],['','True wet','False wet','True dry','False dry','True wet','False wet','True dry','False dry']]
for r in results:rows.append([Paragraph(r['method'],cell)]+[f'{x:.3f}' for x in r['fraction']+r['conditional']])
rows[0]=[Paragraph(x,head) for x in rows[0]];rows[1]=[Paragraph(x,head) for x in rows[1]]
t=Table(rows,colWidths=[167]+[44]*8)
t.setStyle(TableStyle([('SPAN',(1,0),(4,0)),('SPAN',(5,0),(8,0)),('SPAN',(0,0),(0,1)),('LINEABOVE',(0,0),(-1,0),1.2,colors.black),('LINEBELOW',(1,0),(4,0),.5,colors.black),('LINEBELOW',(5,0),(8,0),.5,colors.black),('LINEBELOW',(0,1),(-1,1),.8,colors.black),('LINEBELOW',(0,-1),(-1,-1),1.2,colors.black),('ALIGN',(1,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTNAME',(1,2),(-1,-1),'Helvetica'),('FONTSIZE',(1,2),(-1,-1),9),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
caption='Patch-averaged wet/dry confusion summaries at a threshold of 0.6 mm/h (wet means rainfall greater than or equal to the threshold). In the fraction-of-all-pixels columns, each class is divided by the total number of pixels in each patch before averaging across 100 patches. In the conditional-rate columns, true wet and false dry are normalized by wet ground-truth pixels, while true dry and false wet are normalized by dry ground-truth pixels. Rates are calculated per patch and then averaged; patches with a zero denominator are excluded from the corresponding conditional rate. Values are rounded to three decimal places.'
page=root/'tmp/pdfs/june_wetdry_replacement.pdf'
SimpleDocTemplate(str(page),pagesize=A4,leftMargin=38,rightMargin=38,topMargin=40,bottomMargin=40).build([Paragraph('3. Wet/dry confusion summary',styles['Heading1']),Spacer(1,10),t,Spacer(1,14),Paragraph(caption,styles['BodyText'])])
source=root/'output/pdf/june2023_report_corrected.pdf';out=root/'output/pdf/june2023_report_updated.pdf'
r=PdfReader(source);w=PdfWriter()
for i,p in enumerate(r.pages):w.add_page(PdfReader(page).pages[0] if i==12 else p)
with out.open('wb') as f:w.write(f)
(root/'output/pdf/june2023_wetdry_summary.json').write_text(json.dumps(results,indent=2))
with (root/'output/pdf/june2023_wetdry_patch_counts.csv').open('w') as f:
 wr=csv.DictWriter(f,fieldnames=list(perpatch[0]));wr.writeheader();wr.writerows(perpatch)
with pdfplumber.open(out) as pdf:
 assert len(pdf.pages)==len(r.pages)
 pdf.pages[12].to_image(resolution=140).save('/tmp/june_wetdry_updated.png')
 for i in range(len(r.pages)):
  if i!=12:assert pdf.pages[i].extract_text()==pdfplumber.open(source).pages[i].extract_text()
print(out)
