// Portable product runtime. Browser slides and PPTX consume exactly the same content.json.
import fs from 'node:fs/promises';
import path from 'node:path';
import pptxgen from 'pptxgenjs';

const output = path.resolve(process.argv[2]);
const data = JSON.parse(await fs.readFile(path.join(output, 'content.json'), 'utf8'));
for (const [level, slides] of Object.entries(data.decks)) {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = data.brand;
  pptx.subject = `${level} stakeholder briefing`;
  pptx.title = data.title;
  pptx.lang = 'en-GB';
  pptx.theme = {headFontFace:'Arial', bodyFontFace:'Arial', lang:'en-GB'};
  for (const item of slides) {
    const slide = pptx.addSlide();
    slide.background = {color:'FFFFFF'};
    slide.addText(`${data.brand} · ${level} · ${data.status}`, {
      x:0.65,y:0.25,w:12,h:0.35,fontSize:12,color:data.accent.slice(1),margin:0
    });
    slide.addText(item.title, {
      x:0.65,y:0.85,w:12,h:1.1,fontSize:32,bold:true,color:'172F3C',margin:0,breakLine:false
    });
    let y=2.15;
    for (const line of item.body) {
      slide.addText(line, {x:0.65,y,w:12,h:0.86,fontSize:18,color:'172F3C',margin:0,
                         valign:'top',breakLine:false});
      y+=1.0;
    }
    if (item.image) {
      const imagePath=path.resolve(output,item.image);
      const png = await fs.readFile(imagePath);
      const width = png.readUInt32BE(16), height = png.readUInt32BE(20);
      const scale = Math.min(12 / width, 3.5 / height);
      slide.addImage({path:imagePath, x:0.65, y:3.1, w:width*scale, h:height*scale,
                      altText:'Captured demonstration'});
    }
    if (item.evidence) {
      slide.addText('Execution evidence', {x:0.65,y:6.85,w:9,h:0.3,fontSize:12,
        color:data.accent.slice(1),hyperlink:{url:item.evidence},margin:0});
    }
    slide.addNotes(item.notes);
  }
  await pptx.writeFile({fileName:path.join(output,`${level}.pptx`)});
}
