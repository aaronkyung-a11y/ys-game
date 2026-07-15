from PIL import Image
from collections import deque

# ---------- 1) MAGENTA REMOVAL (fixed) ----------
# Border-only flood fill leaves magenta trapped in enclosed pockets
# (armpits, between arm and torso). Fix: flood fill from border FIRST,
# then sweep any remaining magenta-ish pixels globally — safe because
# the characters contain no magenta in their palette (green/grey/brown/steel).
def is_bg(p):
    r,g,b,a = p[0],p[1],p[2],p[3]
    if a==0: return False
    # magenta = high red, high blue, low green. Loose enough for jpg ringing.
    return r>120 and b>120 and g < min(r,b)*0.72

def key_out(img):
    img=img.convert('RGBA'); w,h=img.size; px=img.load()
    seen=[[False]*h for _ in range(w)]; q=deque()
    for x in range(w):
        for y in (0,h-1):
            if is_bg(px[x,y]) and not seen[x][y]: q.append((x,y)); seen[x][y]=True
    for y in range(h):
        for x in (0,w-1):
            if is_bg(px[x,y]) and not seen[x][y]: q.append((x,y)); seen[x][y]=True
    while q:
        x,y=q.popleft(); px[x,y]=(0,0,0,0)
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx,ny=x+dx,y+dy
            if 0<=nx<w and 0<=ny<h and not seen[nx][ny] and is_bg(px[nx,ny]):
                seen[nx][ny]=True; q.append((nx,ny))
    # sweep trapped pockets
    for y in range(h):
        for x in range(w):
            if is_bg(px[x,y]): px[x,y]=(0,0,0,0)
    # de-fringe: kill semi-transparent magenta halo on edges
    for y in range(h):
        for x in range(w):
            r,g,b,a = px[x,y]
            if a>0 and r>110 and b>110 and g < min(r,b)*0.80:
                px[x,y]=(0,0,0,0)
    return img

def leftover(img):
    px=img.load(); w,h=img.size; n=0
    for y in range(h):
        for x in range(w):
            if is_bg(px[x,y]): n+=1
    return n

# ---------- 2) FACING DETECTION ----------
def eye_side(img):
    """Yellow/red eye marks the facing side."""
    px=img.load(); a=img.split()[3]; bb=a.getbbox()
    if not bb: return None
    x0,y0,x1,y1=bb; midx=(x0+x1)//2
    yb=y0+int((y1-y0)*0.45)
    L=R=0
    for y in range(y0,yb):
        for x in range(x0,x1):
            r,g,b,al=px[x,y]
            if al>0 and ((r>190 and g>140 and b<90) or (r>170 and g<80 and b<80)):
                if x<midx: L+=1
                else: R+=1
    if L+R < 4: return None
    return 'left' if L>R else 'right'

def feet_cx(img):
    a=img.split()[3]; w,h=img.size; bb=a.getbbox()
    if not bb: return w//2
    y0=int(bb[3]-(bb[3]-bb[1])*0.15); xs=[]; px=a.load()
    for y in range(y0,bb[3]):
        for x in range(w):
            if px[x,y]>0: xs.append(x)
    return (min(xs)+max(xs))//2 if xs else (bb[0]+bb[2])//2

CELL=128
# ---------- MANUAL OVERRIDES (user-verified) ----------
# Auto facing detection reads the eye position, which is reliable on WALK rows
# but breaks on ATTACK rows: the body twists and the weapon extends, so the
# "eye is on the facing side" rule stops holding. These were checked in-game.
MANUAL_FLIP = {
    ('GOBLIN', 2),   # attack row inverted by auto-detect (confirmed in-game v0.37)
    # ORC charge row is not auto-built — it uses redrawn art patched in after.
}

def to_cell(f, scale, mirror=False):
    """Fit a sprite into one cell without clipping.

    Two bugs fixed here:
      1. Scaling by HEIGHT only clipped wide poses (weapon thrust sideways is
         wider than tall). Now we fit both axes and take the smaller factor.
      2. Anchoring x on the FEET pushed extended weapons off the cell — the
         feet aren't the centre of the artwork when a sword is out. Anchor on
         the sprite's own bbox centre, then nudge toward the feet only as far
         as there is spare room.
    """
    if mirror: f=f.transpose(Image.FLIP_LEFT_RIGHT)
    bb=f.split()[3].getbbox()
    if not bb: return Image.new('RGBA',(CELL,CELL),(0,0,0,0))
    fc=feet_cx(f); crop=f.crop(bb)
    sc=min((CELL*scale)/crop.height, (CELL*0.88)/crop.width)   # 12% side margin so extended weapons never touch the edge
    nw,nh = max(1,int(crop.width*sc)), max(1,int(crop.height*sc))
    crop=crop.resize((nw,nh),Image.NEAREST)
    cell=Image.new('RGBA',(CELL,CELL),(0,0,0,0))
    # Anchor x on the feet so the character doesn't slide between frames, BUT
    # an attack pose puts the weapon far from the feet: the feet-anchored x
    # then exceeds the spare room and the clamp slams the art flush against
    # the cell edge (looked like the blade was cut off). When the feet anchor
    # doesn't fit, fall back to centring the artwork itself.
    x_feet = int(CELL/2-(fc-bb[0])*sc)
    spare = CELL-nw
    x = x_feet if 0 <= x_feet <= spare else (spare//2)
    y = max(0, min(int(CELL*0.95-nh), CELL-nh))
    cell.paste(crop,(x,y),crop)
    return cell

def build(src, out, scale, label):
    im=Image.open(src); W,H=im.size; cw,ch=W/4,H/3
    raw={}
    for r in range(3):
        for c in range(4):
            raw[(r,c)] = key_out(im.crop((int(c*cw)+6,int(r*ch)+6,int((c+1)*cw)-6,int((r+1)*ch)-6)))
    sheet=Image.new('RGBA',(CELL*4,CELL*3),(0,0,0,0))
    report=[]
    for r in range(3):
        # Pick the source cell for RIGHT: prefer col4, else col3 — whichever
        # actually faces a side. Then mirror it for LEFT. Per-ROW, since
        # Gemini is inconsistent between rows.
        cand=[]
        for c in (3,2):
            s=eye_side(raw[(r,c)])
            if s: cand.append((c,s))
        if cand:
            c_src, facing = cand[0]
            src_cell = raw[(r,c_src)]
            need_mirror_for_right = (facing=='left')   # flip so it faces right
            right_cell = to_cell(src_cell, scale, mirror=need_mirror_for_right)
            left_cell  = to_cell(src_cell, scale, mirror=not need_mirror_for_right)
            report.append(f"row{r+1}: used col{c_src+1} (faced {facing}) -> mirrored={need_mirror_for_right}")
        else:
            # no eye detected: fall back to the mirror decision of the other rows
            right_cell = to_cell(raw[(r,3)], scale, mirror=True)
            left_cell  = to_cell(raw[(r,3)], scale, mirror=False)
            report.append(f"row{r+1}: no eye found -> matched sibling rows (mirrored)")
        sheet.paste(to_cell(raw[(r,0)], scale), (0, r*CELL))   # down
        sheet.paste(to_cell(raw[(r,1)], scale), (1*CELL, r*CELL))  # up
        if (label, r) in MANUAL_FLIP:
            left_cell, right_cell = right_cell, left_cell
            report.append(f"row{r+1}: MANUAL_FLIP applied (verified in-game)")
        sheet.paste(left_cell,  (2*CELL, r*CELL))
        sheet.paste(right_cell, (3*CELL, r*CELL))
    sheet.save(out)
    lm=sum(leftover(sheet.crop((c*CELL,r*CELL,(c+1)*CELL,(r+1)*CELL))) for r in range(3) for c in range(4))
    print(f"\n=== {label} -> {out}")
    for x in report: print("   ", x)
    print(f"    leftover magenta: {lm} px")
    return sheet

build('/mnt/user-data/uploads/1000049640.jpg','/home/claude/sprites/goblin_sheet.png',0.80,'GOBLIN')
build('/mnt/user-data/uploads/1000049655.jpg','/home/claude/sprites/orc_sheet.png',0.84,'ORC')
build('/mnt/user-data/uploads/1000049657.jpg','/home/claude/sprites/thrower_sheet.png',0.78,'THROWER')
