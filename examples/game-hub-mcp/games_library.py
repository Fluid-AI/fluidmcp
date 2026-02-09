"""
Games Library - HTML generators for all 15 games
"""

GAME_LIST = [
    {"id": "snake", "name": "🐍 Snake", "description": "Classic snake game - eat food and grow!"},
    {"id": "space-impact", "name": "🚀 Space Impact", "description": "Shoot enemies in space!"},
    {"id": "sudoku", "name": "🔢 Sudoku", "description": "Fill the grid with numbers 1-9"},
    {"id": "tic-tac-toe", "name": "❌ Tic-Tac-Toe", "description": "Three in a row wins!"},
    {"id": "breakout", "name": "🧱 Breakout", "description": "Break all the bricks!"},
    {"id": "rock-paper-scissors", "name": "✊ Rock-Paper-Scissors", "description": "Beat the computer!"},
    {"id": "pong", "name": "🏓 Pong", "description": "Classic paddle game"},
    {"id": "memory", "name": "🃏 Memory Matching", "description": "Find matching pairs!"},
    {"id": "number-guess", "name": "🎯 Number Guessing", "description": "Guess the secret number!"},
    {"id": "flappy-bird", "name": "🐦 Flappy Bird", "description": "Fly between pipes!"},
    {"id": "minesweeper", "name": "💣 Minesweeper", "description": "Find all the mines!"},
    {"id": "2048", "name": "🔢 2048", "description": "Merge tiles to reach 2048!"},
    {"id": "connect-four", "name": "🔴 Connect Four", "description": "Connect 4 discs to win!"},
    {"id": "whack-a-mole", "name": "🔨 Whack-a-Mole", "description": "Whack as many moles as you can!"},
    {"id": "hangman", "name": "👤 Hangman", "description": "Guess the word before time runs out!"}
]


def generate_snake_html(difficulty="medium", board_size="medium"):
    """Generate Snake game HTML"""
    speed_map = {"easy": 150, "medium": 100, "hard": 50}
    speed = speed_map.get(difficulty, 100)
    size_map = {"small": 20, "medium": 30, "large": 40}
    grid_size = size_map.get(board_size, 30)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Snake Game</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}}.container{{background:white;border-radius:20px;padding:30px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:800px}}h1{{color:#667eea;text-align:center;margin-bottom:20px}}.info{{display:flex;justify-content:space-around;margin-bottom:20px;gap:15px}}.info-box{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:15px 25px;border-radius:10px;font-weight:bold}}#canvas{{border:4px solid #667eea;border-radius:10px;background:#f0f0f0;display:block;margin:0 auto}}.controls{{text-align:center;margin-top:20px}}.btn{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;margin:5px;font-weight:bold}}.btn:hover{{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.3)}}
</style></head><body><div class="container"><h1>🐍 Snake Game</h1><div class="info"><div class="info-box">Score: <span id="score">0</span></div><div class="info-box">High: <span id="high">0</span></div></div><canvas id="canvas"></canvas><div class="controls"><button class="btn" onclick="start()">Start</button><button class="btn" onclick="pause()">Pause</button><button class="btn" onclick="reset()">Reset</button></div></div><script>
const c=document.getElementById('canvas'),ctx=c.getContext('2d'),G={grid_size},S=15;c.width=c.height=G*S;let snake=[{{x:10,y:10}}],dir={{x:1,y:0}},nextDir={{x:1,y:0}},food={{x:15,y:15}},score=0,high=localStorage.getItem('snakeHigh')||0,loop=null,paused=false;document.getElementById('high').textContent=high;document.addEventListener('keydown',e=>{{const k=e.key;if(k==='ArrowUp'||k==='w')dir.y===0&&(nextDir={{x:0,y:-1}});else if(k==='ArrowDown'||k==='s')dir.y===0&&(nextDir={{x:0,y:1}});else if(k==='ArrowLeft'||k==='a')dir.x===0&&(nextDir={{x:-1,y:0}});else if(k==='ArrowRight'||k==='d')dir.x===0&&(nextDir={{x:1,y:0}});e.preventDefault()}});function start(){{if(loop)return;paused=false;loop=setInterval(update,{speed})}}function pause(){{if(loop){{clearInterval(loop);loop=null;paused=true}}else if(paused)start()}}function reset(){{clearInterval(loop);loop=null;snake=[{{x:10,y:10}}];dir={{x:1,y:0}};nextDir={{x:1,y:0}};score=0;document.getElementById('score').textContent=score;spawnFood();draw()}}function update(){{dir=nextDir;const h={{x:snake[0].x+dir.x,y:snake[0].y+dir.y}};if(h.x<0||h.x>=G||h.y<0||h.y>=G||snake.some(s=>s.x===h.x&&s.y===h.y)){{clearInterval(loop);loop=null;alert('Game Over! Score: '+score);return}}snake.unshift(h);if(h.x===food.x&&h.y===food.y){{score+=10;document.getElementById('score').textContent=score;if(score>high){{high=score;localStorage.setItem('snakeHigh',high);document.getElementById('high').textContent=high}}spawnFood()}}else snake.pop();draw()}}function spawnFood(){{do{{food={{x:Math.floor(Math.random()*G),y:Math.floor(Math.random()*G)}}}}while(snake.some(s=>s.x===food.x&&s.y===food.y))}}function draw(){{ctx.fillStyle='#f0f0f0';ctx.fillRect(0,0,c.width,c.height);snake.forEach((s,i)=>{{ctx.fillStyle=i===0?'#667eea':'#8b9eff';ctx.fillRect(s.x*S+1,s.y*S+1,S-2,S-2)}});ctx.fillStyle='#ff4757';ctx.fillRect(food.x*S+1,food.y*S+1,S-2,S-2)}}draw();
</script></body></html>"""


def generate_space_impact_html():
    """Generate Space Impact shooter game"""
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Space Impact</title><style>
*{margin:0;padding:0}body{background:#000;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:Arial}canvas{border:2px solid #0ff;background:#000}.ui{position:absolute;top:20px;left:20px;color:#0ff;font-size:20px;text-shadow:0 0 10px #0ff}
</style></head><body><div class="ui">Score: <span id="score">0</span> | Lives: <span id="lives">3</span></div><canvas id="c"></canvas><script>
const c=document.getElementById('c'),ctx=c.getContext('2d');c.width=800;c.height=600;let player={x:50,y:300,w:40,h:30,speed:5},bullets=[],enemies=[],score=0,lives=3,keys={};document.addEventListener('keydown',e=>keys[e.key]=true);document.addEventListener('keyup',e=>keys[e.key]=false);function shoot(){bullets.push({x:player.x+player.w,y:player.y+player.h/2-2,w:10,h:4,speed:8})}setInterval(()=>{if(Math.random()<0.02)enemies.push({x:c.width,y:Math.random()*(c.height-40),w:30,h:30,speed:2+Math.random()*2})},500);function update(){if(keys.ArrowUp||keys.w)player.y=Math.max(0,player.y-player.speed);if(keys.ArrowDown||keys.s)player.y=Math.min(c.height-player.h,player.y+player.speed);if(keys[' '])shoot(),keys[' ']=false;bullets=bullets.filter(b=>{b.x+=b.speed;return b.x<c.width}).filter(b=>{const hit=enemies.find(e=>b.x<e.x+e.w&&b.x+b.w>e.x&&b.y<e.y+e.h&&b.y+b.h>e.y);if(hit){enemies=enemies.filter(e=>e!==hit);score+=10;document.getElementById('score').textContent=score;return false}return true});enemies=enemies.filter(e=>{e.x-=e.speed;if(e.x+e.w<0)return false;if(e.x<player.x+player.w&&e.x+e.w>player.x&&e.y<player.y+player.h&&e.y+e.h>player.y){lives--;document.getElementById('lives').textContent=lives;if(lives<=0){alert('Game Over! Score: '+score);location.reload()}return false}return true})}function draw(){ctx.fillStyle='#000';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#0ff';ctx.fillRect(player.x,player.y,player.w,player.h);ctx.fillStyle='#ff0';bullets.forEach(b=>ctx.fillRect(b.x,b.y,b.w,b.h));ctx.fillStyle='#f00';enemies.forEach(e=>ctx.fillRect(e.x,e.y,e.w,e.h))}function loop(){update();draw();requestAnimationFrame(loop)}loop();
</script></body></html>"""


def generate_tic_tac_toe_html():
    """Generate Tic-Tac-Toe game"""
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Tic-Tac-Toe</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:30px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.board{display:grid;grid-template-columns:repeat(3,120px);gap:10px;margin:20px 0}.cell{width:120px;height:120px;background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:10px;font-size:48px;color:white;cursor:pointer;transition:transform 0.2s}.cell:hover{transform:scale(1.05)}.cell:disabled{cursor:not-allowed;opacity:0.7}.status{text-align:center;font-size:20px;margin:20px 0;color:#667eea;font-weight:bold}.btn{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;font-size:16px;margin-top:10px}.btn:hover{background:#764ba2}
</style></head><body><div class="container"><h1>❌ Tic-Tac-Toe</h1><div class="status" id="status">Player X's turn</div><div class="board" id="board"></div><button class="btn" onclick="reset()">New Game</button></div><script>
let board=['','','','','','','','',''],currentPlayer='X',gameActive=true;const winPatterns=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];function init(){const b=document.getElementById('board');b.innerHTML='';board.forEach((v,i)=>{const cell=document.createElement('button');cell.className='cell';cell.onclick=()=>makeMove(i);b.appendChild(cell)})}function makeMove(i){if(!gameActive||board[i])return;board[i]=currentPlayer;update();if(checkWin()){document.getElementById('status').textContent='Player '+currentPlayer+' wins!';gameActive=false;return}if(board.every(c=>c)){document.getElementById('status').textContent="It's a draw!";gameActive=false;return}currentPlayer=currentPlayer==='X'?'O':'X';document.getElementById('status').textContent='Player '+currentPlayer+"'s turn"}function checkWin(){return winPatterns.some(pattern=>board[pattern[0]]&&board[pattern[0]]===board[pattern[1]]&&board[pattern[0]]===board[pattern[2]])}function update(){document.querySelectorAll('.cell').forEach((cell,i)=>{cell.textContent=board[i];cell.disabled=!!board[i]||!gameActive})}function reset(){board=['','','','','','','','',''];currentPlayer='X';gameActive=true;document.getElementById('status').textContent="Player X's turn";init()}init();
</script></body></html>"""


def generate_breakout_html():
    """Generate Breakout brick breaker game"""
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Breakout</title><style>
*{margin:0;padding:0}body{background:#1a1a2e;display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column;font-family:Arial}canvas{border:2px solid #667eea;background:#0f0f1e;border-radius:10px}.info{color:#667eea;font-size:20px;margin:20px;text-align:center}
</style></head><body><div class="info">Score: <span id="score">0</span> | Lives: <span id="lives">3</span></div><canvas id="c"></canvas><script>
const c=document.getElementById('c'),ctx=c.getContext('2d');c.width=800;c.height=600;let paddle={x:350,y:550,w:100,h:15,speed:8},ball={x:400,y:300,dx:4,dy:-4,r:8},bricks=[],score=0,lives=3;for(let r=0;r<5;r++)for(let col=0;col<10;col++)bricks.push({x:col*80+35,y:r*30+50,w:70,h:25,hit:false});document.addEventListener('mousemove',e=>{const rect=c.getBoundingClientRect();paddle.x=e.clientX-rect.left-paddle.w/2;paddle.x=Math.max(0,Math.min(c.width-paddle.w,paddle.x))});function update(){ball.x+=ball.dx;ball.y+=ball.dy;if(ball.x-ball.r<0||ball.x+ball.r>c.width)ball.dx=-ball.dx;if(ball.y-ball.r<0)ball.dy=-ball.dy;if(ball.y+ball.r>paddle.y&&ball.y-ball.r<paddle.y+paddle.h&&ball.x>paddle.x&&ball.x<paddle.x+paddle.w){ball.dy=-ball.dy;ball.y=paddle.y-ball.r}if(ball.y+ball.r>c.height){lives--;document.getElementById('lives').textContent=lives;if(lives<=0){alert('Game Over! Score: '+score);location.reload()}ball.x=400;ball.y=300;ball.dx=4;ball.dy=-4}bricks.forEach(b=>{if(!b.hit&&ball.x>b.x&&ball.x<b.x+b.w&&ball.y>b.y&&ball.y<b.y+b.h){b.hit=true;ball.dy=-ball.dy;score+=10;document.getElementById('score').textContent=score}})}function draw(){ctx.fillStyle='#0f0f1e';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#667eea';ctx.fillRect(paddle.x,paddle.y,paddle.w,paddle.h);ctx.fillStyle='#ff4757';ctx.beginPath();ctx.arc(ball.x,ball.y,ball.r,0,Math.PI*2);ctx.fill();bricks.forEach(b=>{if(!b.hit){ctx.fillStyle='#8b5cf6';ctx.fillRect(b.x,b.y,b.w,b.h)}})}function loop(){update();draw();requestAnimationFrame(loop)}loop();
</script></body></html>"""


def generate_2048_html():
    """Generate 2048 tile game"""
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>2048</title><style>
*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial;background:#faf8ef;display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:#bbada0;padding:15px;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(4,100px);gap:15px;background:#bbada0;padding:15px;border-radius:10px}.cell{width:100px;height:100px;background:#cdc1b4;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:bold;color:#776e65}.tile-2{background:#eee4da}.tile-4{background:#ede0c8}.tile-8{background:#f2b179;color:#f9f6f2}.tile-16{background:#f59563;color:#f9f6f2}.tile-32{background:#f67c5f;color:#f9f6f2}.tile-64{background:#f65e3b;color:#f9f6f2}.tile-128{background:#edcf72;color:#f9f6f2;font-size:28px}.tile-256{background:#edcc61;color:#f9f6f2;font-size:28px}.tile-512{background:#edc850;color:#f9f6f2;font-size:28px}.tile-1024{background:#edc53f;color:#f9f6f2;font-size:24px}.tile-2048{background:#edc22e;color:#f9f6f2;font-size:24px}.score{text-align:center;margin:20px;font-size:24px;color:#776e65}.btn{background:#8f7a66;color:#f9f6f2;border:none;padding:12px 30px;border-radius:5px;cursor:pointer;font-size:16px;margin:10px}.btn:hover{background:#9f8a76}
</style></head><body><div class="container"><div class="score">Score: <span id="score">0</span></div><div class="grid" id="grid"></div><button class="btn" onclick="init()">New Game</button></div><script>
let grid=[],score=0;function init(){grid=Array(4).fill().map(()=>Array(4).fill(0));score=0;document.getElementById('score').textContent=score;addTile();addTile();render()}function addTile(){const empty=[];grid.forEach((row,r)=>row.forEach((v,c)=>{if(!v)empty.push({r,c})}));if(empty.length){const{r,c}=empty[Math.floor(Math.random()*empty.length)];grid[r][c]=Math.random()<0.9?2:4}}function move(dir){let moved=false,newGrid=grid.map(r=>[...r]);if(dir==='left'||dir==='right'){newGrid.forEach((row,r)=>{let arr=row.filter(v=>v);if(dir==='right')arr.reverse();for(let i=0;i<arr.length-1;i++){if(arr[i]===arr[i+1]){arr[i]*=2;score+=arr[i];arr.splice(i+1,1);moved=true}}while(arr.length<4)arr.push(0);if(dir==='right')arr.reverse();if(arr.some((v,i)=>v!==row[i]))moved=true;newGrid[r]=arr})}else{for(let c=0;c<4;c++){let arr=newGrid.map(r=>r[c]).filter(v=>v);if(dir==='down')arr.reverse();for(let i=0;i<arr.length-1;i++){if(arr[i]===arr[i+1]){arr[i]*=2;score+=arr[i];arr.splice(i+1,1);moved=true}}while(arr.length<4)arr.push(0);if(dir==='down')arr.reverse();if(arr.some((v,i)=>v!==newGrid[i][c]))moved=true;arr.forEach((v,r)=>newGrid[r][c]=v)}}if(moved){grid=newGrid;addTile();render();document.getElementById('score').textContent=score}}function render(){const g=document.getElementById('grid');g.innerHTML='';grid.forEach(row=>row.forEach(v=>{const cell=document.createElement('div');cell.className='cell'+(v?' tile-'+v:'');cell.textContent=v||'';g.appendChild(cell)}))}document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')move('left');else if(e.key==='ArrowRight')move('right');else if(e.key==='ArrowUp')move('up');else if(e.key==='ArrowDown')move('down')});init();
</script></body></html>"""


def generate_memory_html():
    """Generate Memory matching game"""
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Memory Game</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:30px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(4,100px);gap:10px}.card{width:100px;height:100px;background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:10px;font-size:40px;cursor:pointer;transition:transform 0.3s}.card.flipped{background:white;color:#667eea}.card:hover{transform:scale(1.05)}.stats{text-align:center;margin:20px;font-size:18px;color:#667eea}.btn{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;font-size:16px;margin-top:10px}
</style></head><body><div class="container"><h1>🃏 Memory Game</h1><div class="stats">Moves: <span id="moves">0</span> | Matched: <span id="matched">0</span>/8</div><div class="grid" id="grid"></div><button class="btn" onclick="init()">New Game</button></div><script>
const symbols=['🍎','🍌','🍇','🍊','🍓','🍉','🍒','🍑'];let cards=[],flipped=[],matched=0,moves=0;function init(){cards=[...symbols,...symbols].sort(()=>Math.random()-0.5);flipped=[];matched=0;moves=0;document.getElementById('moves').textContent=moves;document.getElementById('matched').textContent=matched;const g=document.getElementById('grid');g.innerHTML='';cards.forEach((s,i)=>{const c=document.createElement('button');c.className='card';c.dataset.index=i;c.onclick=()=>flip(i);g.appendChild(c)})}function flip(i){if(flipped.length===2||flipped.includes(i)||document.querySelector(`[data-index="${i}"]`).classList.contains('matched'))return;flipped.push(i);const c=document.querySelector(`[data-index="${i}"]`);c.classList.add('flipped');c.textContent=cards[i];if(flipped.length===2){moves++;document.getElementById('moves').textContent=moves;if(cards[flipped[0]]===cards[flipped[1]]){matched++;document.getElementById('matched').textContent=matched;flipped.forEach(idx=>document.querySelector(`[data-index="${idx}"]`).classList.add('matched'));flipped=[];if(matched===8)setTimeout(()=>alert('You won in '+moves+' moves!'),500)}else{setTimeout(()=>{flipped.forEach(idx=>{const c=document.querySelector(`[data-index="${idx}"]`);c.classList.remove('flipped');c.textContent=''});flipped=[]},1000)}}}init();
</script></body></html>"""


def generate_simple_game_menu():
    """Generate a simple menu showing all 15 games"""
    games_html = ""
    for game in GAME_LIST:
        games_html += f'<div class="game-card" onclick="selectGame(\'{game["id"]}\')">'
        games_html += f'<div class="game-icon">{game["name"].split()[0]}</div>'
        games_html += f'<div class="game-title">{game["name"]}</div>'
        games_html += f'<div class="game-desc">{game["description"]}</div>'
        games_html += '</div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Game Hub</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:40px}}.container{{max-width:1200px;margin:0 auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}}h1{{color:#667eea;text-align:center;font-size:3em;margin-bottom:10px}}h2{{color:#764ba2;text-align:center;margin-bottom:40px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}}.game-card{{background:linear-gradient(135deg,#667eea,#764ba2);padding:25px;border-radius:15px;cursor:pointer;transition:transform 0.3s,box-shadow 0.3s;color:white;text-align:center}}.game-card:hover{{transform:translateY(-5px);box-shadow:0 10px 30px rgba(0,0,0,0.3)}}.game-icon{{font-size:3em;margin-bottom:10px}}.game-title{{font-size:1.3em;font-weight:bold;margin-bottom:10px}}.game-desc{{font-size:0.9em;opacity:0.9}}
</style></head><body><div class="container"><h1>🎮 Game Hub</h1><h2>Choose a game to play!</h2><div class="grid">{games_html}</div></div><script>
function selectGame(id){{alert('To play '+id+', call the play_game tool with game_name: "'+id+'"');}}
</script></body></html>"""
