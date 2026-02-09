#!/usr/bin/env python3
"""
Game Hub MCP Server
Provides 15 interactive games through MCP tools
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

from games_library import (
    GAME_LIST,
    generate_snake_html,
    generate_space_impact_html,
    generate_tic_tac_toe_html,
    generate_breakout_html,
    generate_2048_html,
    generate_memory_html,
    generate_simple_game_menu
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("game-hub-mcp")

# Initialize MCP server
app = Server("game-hub")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available game tools"""
    return [
        Tool(
            name="list_games",
            description="Show all 15 available games to play. Use this when user asks 'I want to play a game' or wants to see game options. IMPORTANT: After calling this tool, you MUST copy the full game list from the observation into your answer section to show the user. DO NOT just say 'I am transferring you to the next agent'. Instead, present the game list with a friendly prompt like 'Here are 15 games you can choose from: [paste full list]. Which one would you like to play?'",
            inputSchema={
                "type": "object",
                "properties": {
                    "show_all": {
                        "type": "boolean",
                        "description": "Always set to true (parameter exists for compatibility)",
                        "default": True
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="play_game",
            description="Start playing a specific game by name. Returns interactive HTML game. IMPORTANT: After calling this tool, provide context in your answer like 'Here's [Game Name]! [Brief controls/instructions]. Have fun!' DO NOT just say 'I am transferring you to the next agent'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Name of the game to play",
                        "enum": [
                            "snake", "space-impact", "sudoku", "tic-tac-toe", "breakout",
                            "rock-paper-scissors", "pong", "memory", "number-guess",
                            "flappy-bird", "minesweeper", "2048", "connect-four",
                            "whack-a-mole", "hangman"
                        ]
                    },
                    "difficulty": {
                        "type": "string",
                        "description": "Difficulty level (for games that support it)",
                        "enum": ["easy", "medium", "hard"],
                        "default": "medium"
                    }
                },
                "required": ["game_name"]
            }
        )
    ]


def generate_remaining_games(game_name: str) -> str:
    """Generate HTML for the remaining games"""

    if game_name == "sudoku":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Sudoku</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:30px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(9,40px);gap:2px;background:#667eea;padding:2px;margin:20px 0}input{width:40px;height:40px;text-align:center;font-size:20px;border:1px solid #ddd;font-weight:bold}input:disabled{background:#f0f0f0}.btn{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;margin:5px}
</style></head><body><div class="container"><h1>🔢 Sudoku</h1><div class="grid" id="grid"></div><div><button class="btn" onclick="init()">New Puzzle</button><button class="btn" onclick="solve()">Show Solution</button></div></div><script>
const puzzle=[[5,3,0,0,7,0,0,0,0],[6,0,0,1,9,5,0,0,0],[0,9,8,0,0,0,0,6,0],[8,0,0,0,6,0,0,0,3],[4,0,0,8,0,3,0,0,1],[7,0,0,0,2,0,0,0,6],[0,6,0,0,0,0,2,8,0],[0,0,0,4,1,9,0,0,5],[0,0,0,0,8,0,0,7,9]];const solution=[[5,3,4,6,7,8,9,1,2],[6,7,2,1,9,5,3,4,8],[1,9,8,3,4,2,5,6,7],[8,5,9,7,6,1,4,2,3],[4,2,6,8,5,3,7,9,1],[7,1,3,9,2,4,8,5,6],[9,6,1,5,3,7,2,8,4],[2,8,7,4,1,9,6,3,5],[3,4,5,2,8,6,1,7,9]];function init(){const g=document.getElementById('grid');g.innerHTML='';puzzle.forEach((row,r)=>row.forEach((v,c)=>{const inp=document.createElement('input');inp.maxLength=1;inp.value=v||'';inp.disabled=!!v;if(v)inp.style.color='#667eea';g.appendChild(inp)}))}function solve(){const inputs=document.querySelectorAll('input');inputs.forEach((inp,i)=>{const r=Math.floor(i/9),c=i%9;inp.value=solution[r][c]})}init();
</script></body></html>"""

    elif game_name == "rock-paper-scissors":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Rock Paper Scissors</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh}.container{background:white;padding:40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);text-align:center}h1{color:#667eea;margin-bottom:30px}.choices{display:flex;gap:20px;margin:30px 0}.choice{font-size:4em;cursor:pointer;padding:20px;border-radius:50%;background:#f0f0f0;transition:transform 0.2s}.choice:hover{transform:scale(1.2);background:#667eea}.result{font-size:1.5em;margin:20px;color:#667eea;min-height:60px}.scores{display:flex;justify-content:space-around;margin-top:20px;font-size:1.2em}.score{color:#764ba2;font-weight:bold}
</style></head><body><div class="container"><h1>✊ Rock Paper Scissors</h1><div class="choices"><div class="choice" onclick="play('rock')">✊</div><div class="choice" onclick="play('paper')">✋</div><div class="choice" onclick="play('scissors')">✌️</div></div><div class="result" id="result">Choose your move!</div><div class="scores"><div>You: <span class="score" id="you">0</span></div><div>Computer: <span class="score" id="cpu">0</span></div></div></div><script>
let scores={you:0,cpu:0};function play(choice){const choices=['rock','paper','scissors'];const cpu=choices[Math.floor(Math.random()*3)];const emoji={rock:'✊',paper:'✋',scissors:'✌️'};let result='';if(choice===cpu)result='Draw!';else if((choice==='rock'&&cpu==='scissors')||(choice==='paper'&&cpu==='rock')||(choice==='scissors'&&cpu==='paper')){result='You Win!';scores.you++}else{result='Computer Wins!';scores.cpu++}document.getElementById('result').innerHTML=`You: ${emoji[choice]} vs Computer: ${emoji[cpu]}<br>${result}`;document.getElementById('you').textContent=scores.you;document.getElementById('cpu').textContent=scores.cpu}
</script></body></html>"""

    elif game_name == "pong":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Pong</title><style>
*{margin:0;padding:0}body{background:#000;display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column;font-family:Arial}canvas{border:2px solid #fff;background:#000}.score{color:#fff;font-size:24px;margin:20px}
</style></head><body><div class="score"><span id="p1">0</span> : <span id="p2">0</span></div><canvas id="c"></canvas><script>
const c=document.getElementById('c'),ctx=c.getContext('2d');c.width=800;c.height=600;let p1={x:10,y:250,w:10,h:100,score:0},p2={x:780,y:250,w:10,h:100,score:0},ball={x:400,y:300,dx:5,dy:3,r:8};document.addEventListener('mousemove',e=>{const rect=c.getBoundingClientRect();p1.y=e.clientY-rect.top-p1.h/2;p1.y=Math.max(0,Math.min(c.height-p1.h,p1.y))});function update(){ball.x+=ball.dx;ball.y+=ball.dy;if(ball.y-ball.r<0||ball.y+ball.r>c.height)ball.dy=-ball.dy;if(ball.x-ball.r<p1.x+p1.w&&ball.y>p1.y&&ball.y<p1.y+p1.h)ball.dx=-ball.dx;if(ball.x+ball.r>p2.x&&ball.y>p2.y&&ball.y<p2.y+p2.h)ball.dx=-ball.dx;if(ball.x<0){p2.score++;document.getElementById('p2').textContent=p2.score;ball.x=400;ball.y=300}if(ball.x>c.width){p1.score++;document.getElementById('p1').textContent=p1.score;ball.x=400;ball.y=300}p2.y+=(ball.y-(p2.y+p2.h/2))*0.1;p2.y=Math.max(0,Math.min(c.height-p2.h,p2.y))}function draw(){ctx.fillStyle='#000';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#fff';ctx.fillRect(p1.x,p1.y,p1.w,p1.h);ctx.fillRect(p2.x,p2.y,p2.w,p2.h);ctx.beginPath();ctx.arc(ball.x,ball.y,ball.r,0,Math.PI*2);ctx.fill();ctx.setLineDash([10,10]);ctx.beginPath();ctx.moveTo(c.width/2,0);ctx.lineTo(c.width/2,c.height);ctx.strokeStyle='#fff';ctx.stroke()}function loop(){update();draw();requestAnimationFrame(loop)}loop();
</script></body></html>"""

    elif game_name == "number-guess":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Number Guessing Game</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh}.container{background:white;padding:50px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);text-align:center;max-width:500px}h1{color:#667eea;margin-bottom:20px}input{padding:15px;font-size:20px;border:2px solid #667eea;border-radius:10px;width:200px;margin:20px 0;text-align:center}button{background:#667eea;color:white;border:none;padding:15px 40px;border-radius:25px;cursor:pointer;font-size:18px;margin:10px}button:hover{background:#764ba2}.message{margin:20px 0;font-size:1.3em;color:#667eea;min-height:30px}.attempts{color:#764ba2;font-size:1.1em;margin:10px}
</style></head><body><div class="container"><h1>🎯 Number Guessing Game</h1><p>Guess a number between 1 and 100</p><input type="number" id="guess" min="1" max="100" placeholder="Enter your guess"><br><button onclick="check()">Guess</button><button onclick="init()">New Game</button><div class="message" id="msg"></div><div class="attempts">Attempts: <span id="attempts">0</span></div></div><script>
let target,attempts;function init(){target=Math.floor(Math.random()*100)+1;attempts=0;document.getElementById('msg').textContent='';document.getElementById('attempts').textContent=0;document.getElementById('guess').value=''}function check(){const guess=parseInt(document.getElementById('guess').value);if(!guess||guess<1||guess>100){document.getElementById('msg').textContent='Please enter a number between 1 and 100';return}attempts++;document.getElementById('attempts').textContent=attempts;if(guess===target){document.getElementById('msg').innerHTML=`🎉 Correct! You won in ${attempts} attempts!`;setTimeout(init,3000)}else if(guess<target){document.getElementById('msg').textContent='📈 Too low! Try higher'}else{document.getElementById('msg').textContent='📉 Too high! Try lower'}}init();
</script></body></html>"""

    elif game_name == "flappy-bird":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Flappy Bird</title><style>
*{margin:0;padding:0}body{background:#4ec0ca;display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column;font-family:Arial}canvas{border:3px solid #000;background:linear-gradient(180deg,#4ec0ca 0%,#87ceeb 50%,#deb887 100%)}.score{color:#fff;font-size:28px;margin:20px;text-shadow:2px 2px 4px #000}
</style></head><body><div class="score">Score: <span id="score">0</span></div><canvas id="c"></canvas><script>
const c=document.getElementById('c'),ctx=c.getContext('2d');c.width=400;c.height=600;let bird={x:50,y:300,vy:0,r:15},pipes=[],score=0,gameOver=false;document.addEventListener('click',()=>{if(!gameOver)bird.vy=-8});setInterval(()=>{if(!gameOver&&Math.random()<0.5)pipes.push({x:c.width,gap:200,y:Math.random()*(c.height-300)+100})},2000);function update(){if(gameOver)return;bird.vy+=0.5;bird.y+=bird.vy;if(bird.y<0||bird.y>c.height-bird.r){gameOver=true;alert('Game Over! Score: '+score);location.reload()}pipes=pipes.filter(p=>{p.x-=3;if(p.x+50<0){score++;document.getElementById('score').textContent=score;return false}if(bird.x+bird.r>p.x&&bird.x-bird.r<p.x+50){if(bird.y-bird.r<p.y||bird.y+bird.r>p.y+p.gap){gameOver=true;alert('Game Over! Score: '+score);location.reload()}}return true})}function draw(){ctx.fillStyle='#87ceeb';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#ffd700';ctx.beginPath();ctx.arc(bird.x,bird.y,bird.r,0,Math.PI*2);ctx.fill();ctx.fillStyle='#228b22';pipes.forEach(p=>{ctx.fillRect(p.x,0,50,p.y);ctx.fillRect(p.x,p.y+p.gap,50,c.height-p.y-p.gap)})}function loop(){update();draw();requestAnimationFrame(loop)}loop();
</script></body></html>"""

    elif game_name == "minesweeper":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Minesweeper</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:30px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(10,40px);gap:2px}.cell{width:40px;height:40px;background:#ccc;border:2px outset #999;display:flex;align-items:center;justify-content:center;cursor:pointer;font-weight:bold}.cell:hover{background:#ddd}.cell.revealed{background:#fff;border:1px solid #999;cursor:default}.cell.mine{background:#f00;color:#fff}.info{text-align:center;margin:20px;color:#667eea;font-size:18px}.btn{background:#667eea;color:white;border:none;padding:10px 25px;border-radius:20px;cursor:pointer;margin:5px}
</style></head><body><div class="container"><h1>💣 Minesweeper</h1><div class="info">Mines: <span id="mines">10</span> | Flags: <span id="flags">0</span></div><div class="grid" id="grid"></div><button class="btn" onclick="init()">New Game</button></div><script>
const SIZE=10,MINES=10;let grid=[],revealed=0,flags=0;function init(){grid=Array(SIZE).fill().map(()=>Array(SIZE).fill(0));let placed=0;while(placed<MINES){const r=Math.floor(Math.random()*SIZE),c=Math.floor(Math.random()*SIZE);if(grid[r][c]!==9){grid[r][c]=9;placed++;for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){const nr=r+dr,nc=c+dc;if(nr>=0&&nr<SIZE&&nc>=0&&nc<SIZE&&grid[nr][nc]!==9)grid[nr][nc]++}}}revealed=0;flags=0;document.getElementById('flags').textContent=flags;render()}function render(){const g=document.getElementById('grid');g.innerHTML='';grid.forEach((row,r)=>row.forEach((v,c)=>{const cell=document.createElement('div');cell.className='cell';cell.dataset.r=r;cell.dataset.c=c;cell.onclick=()=>reveal(r,c);cell.oncontextmenu=e=>{e.preventDefault();flag(r,c)};g.appendChild(cell)}))}function reveal(r,c){const cell=document.querySelector(`[data-r="${r}"][data-c="${c}"]`);if(cell.classList.contains('revealed')||cell.textContent==='🚩')return;cell.classList.add('revealed');revealed++;if(grid[r][c]===9){cell.classList.add('mine');cell.textContent='💣';alert('Game Over!');init();return}if(grid[r][c]>0)cell.textContent=grid[r][c];else{for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){const nr=r+dr,nc=c+dc;if(nr>=0&&nr<SIZE&&nc>=0&&nc<SIZE)reveal(nr,nc)}}if(revealed===SIZE*SIZE-MINES)alert('You Win!')}function flag(r,c){const cell=document.querySelector(`[data-r="${r}"][data-c="${c}"]`);if(cell.classList.contains('revealed'))return;if(cell.textContent==='🚩'){cell.textContent='';flags--}else{cell.textContent='🚩';flags++}document.getElementById('flags').textContent=flags}init();
</script></body></html>"""

    elif game_name == "connect-four":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Connect Four</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:30px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(7,70px);gap:8px;background:#0066cc;padding:10px;border-radius:10px}.cell{width:70px;height:70px;background:#fff;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:50px}.status{text-align:center;margin:20px;color:#667eea;font-size:20px}.btn{background:#667eea;color:white;border:none;padding:10px 25px;border-radius:20px;cursor:pointer}
</style></head><body><div class="container"><h1>🔴 Connect Four</h1><div class="status" id="status">Red's turn</div><div class="grid" id="grid"></div><button class="btn" onclick="init()">New Game</button></div><script>
const ROWS=6,COLS=7;let board=Array(ROWS).fill().map(()=>Array(COLS).fill(0)),current=1;function init(){board=Array(ROWS).fill().map(()=>Array(COLS).fill(0));current=1;document.getElementById('status').textContent="Red's turn";render()}function render(){const g=document.getElementById('grid');g.innerHTML='';for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++){const cell=document.createElement('div');cell.className='cell';cell.onclick=()=>drop(c);if(board[r][c]===1)cell.textContent='🔴';else if(board[r][c]===2)cell.textContent='🟡';g.appendChild(cell)}}function drop(c){for(let r=ROWS-1;r>=0;r--){if(board[r][c]===0){board[r][c]=current;if(checkWin(r,c)){alert((current===1?'Red':'Yellow')+' wins!');init();return}current=current===1?2:1;document.getElementById('status').textContent=(current===1?'Red':'Yellow')+"'s turn";render();return}}}function checkWin(r,c){const dirs=[[0,1],[1,0],[1,1],[1,-1]];return dirs.some(([dr,dc])=>{let count=1;for(let d of[-1,1]){let nr=r+dr*d,nc=c+dc*d;while(nr>=0&&nr<ROWS&&nc>=0&&nc<COLS&&board[nr][nc]===board[r][c]){count++;nr+=dr*d;nc+=dc*d}}return count>=4})}init();
</script></body></html>"""

    elif game_name == "whack-a-mole":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Whack-a-Mole</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(3,120px);gap:20px;margin:20px 0}.hole{width:120px;height:120px;background:#8b4513;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:60px;position:relative}.hole.active{background:#d2691e}.info{text-align:center;color:#667eea;font-size:20px;margin:20px}.btn{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;margin:5px}
</style></head><body><div class="container"><h1>🔨 Whack-a-Mole</h1><div class="info">Score: <span id="score">0</span> | Time: <span id="time">30</span>s</div><div class="grid" id="grid"></div><button class="btn" onclick="start()">Start Game</button></div><script>
let score=0,time=30,interval,moleInterval,active=false;function init(){const g=document.getElementById('grid');g.innerHTML='';for(let i=0;i<9;i++){const hole=document.createElement('div');hole.className='hole';hole.dataset.id=i;hole.onclick=()=>whack(i);g.appendChild(hole)}}function start(){if(active)return;active=true;score=0;time=30;document.getElementById('score').textContent=score;document.getElementById('time').textContent=time;interval=setInterval(()=>{time--;document.getElementById('time').textContent=time;if(time<=0){clearInterval(interval);clearInterval(moleInterval);active=false;alert('Game Over! Score: '+score)}},1000);moleInterval=setInterval(showMole,800)}function showMole(){if(!active)return;document.querySelectorAll('.hole').forEach(h=>h.classList.remove('active'));const id=Math.floor(Math.random()*9);const hole=document.querySelector(`[data-id="${id}"]`);hole.classList.add('active');hole.textContent='🦔';setTimeout(()=>{hole.classList.remove('active');hole.textContent=''},600)}function whack(id){const hole=document.querySelector(`[data-id="${id}"]`);if(hole.classList.contains('active')){score+=10;document.getElementById('score').textContent=score;hole.classList.remove('active');hole.textContent=''}}init();
</script></body></html>"""

    elif game_name == "hangman":
        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Hangman</title><style>
*{margin:0;padding:0}body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}.container{background:white;padding:40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);text-align:center}h1{color:#667eea;margin-bottom:20px}.word{font-size:2.5em;letter-spacing:10px;margin:30px;color:#667eea;font-weight:bold}.keyboard{display:grid;grid-template-columns:repeat(7,50px);gap:8px;justify-content:center;margin:20px}.key{width:50px;height:50px;background:#667eea;color:white;border:none;border-radius:8px;cursor:pointer;font-size:18px;font-weight:bold}.key:disabled{background:#ccc;cursor:not-allowed}.info{margin:20px;color:#764ba2;font-size:18px}.btn{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:25px;cursor:pointer;margin:10px}
</style></head><body><div class="container"><h1>👤 Hangman</h1><div class="info">Wrong: <span id="wrong">0</span>/6</div><div class="word" id="word"></div><div class="keyboard" id="keyboard"></div><button class="btn" onclick="init()">New Word</button></div><script>
const words=['JAVASCRIPT','PYTHON','CODING','COMPUTER','ALGORITHM','DATABASE','FUNCTION','VARIABLE'];let word='',guessed=[],wrong=0;function init(){word=words[Math.floor(Math.random()*words.length)];guessed=[];wrong=0;document.getElementById('wrong').textContent=wrong;renderWord();renderKeyboard()}function renderWord(){const display=word.split('').map(l=>guessed.includes(l)?l:'_').join(' ');document.getElementById('word').textContent=display;if(!display.includes('_')){setTimeout(()=>alert('You Win!'),100);setTimeout(init,1000)}}function renderKeyboard(){const k=document.getElementById('keyboard');k.innerHTML='';'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').forEach(l=>{const btn=document.createElement('button');btn.className='key';btn.textContent=l;btn.onclick=()=>guess(l);if(guessed.includes(l))btn.disabled=true;k.appendChild(btn)})}function guess(l){if(guessed.includes(l))return;guessed.push(l);if(!word.includes(l)){wrong++;document.getElementById('wrong').textContent=wrong;if(wrong>=6){alert('Game Over! Word was: '+word);init();return}}renderWord();renderKeyboard()}init();
</script></body></html>"""

    return "<h1>Game not found</h1>"


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        # Ensure arguments is never None
        if arguments is None:
            arguments = {}

        if name == "list_games":
            logger.info("Listing all available games")

            # Build the game list
            game_list = ""
            for i, game in enumerate(GAME_LIST, 1):
                game_list += f"{i}. {game['name']} - {game['description']}\n"

            # Return with explicit answer instruction embedded
            text = f"AGENT_INSTRUCTION: You must copy this exact text to your answer field:\n\nHere are 15 games you can play:\n\n{game_list}\nWhich game would you like to play? Just tell me the name or number!"

            return [TextContent(type="text", text=text)]

        elif name == "play_game":
            game_name_input = arguments.get("game_name", "").lower()
            difficulty = arguments.get("difficulty", "medium")

            # Map display names to game IDs
            name_mapping = {
                "snake": "snake",
                "space impact": "space-impact",
                "sudoku": "sudoku",
                "tic-tac-toe": "tic-tac-toe",
                "tic tac toe": "tic-tac-toe",
                "breakout": "breakout",
                "brick breaker": "breakout",
                "rock-paper-scissors": "rock-paper-scissors",
                "rock paper scissors": "rock-paper-scissors",
                "pong": "pong",
                "memory": "memory",
                "memory matching": "memory",
                "number-guess": "number-guess",
                "number guessing": "number-guess",
                "guess the number": "number-guess",
                "flappy-bird": "flappy-bird",
                "flappy bird": "flappy-bird",
                "minesweeper": "minesweeper",
                "mines": "minesweeper",
                "2048": "2048",
                "connect-four": "connect-four",
                "connect four": "connect-four",
                "connect 4": "connect-four",
                "whack-a-mole": "whack-a-mole",
                "whack a mole": "whack-a-mole",
                "hangman": "hangman"
            }

            # Get the correct game ID
            game_name = name_mapping.get(game_name_input, game_name_input)

            logger.info(f"Starting game: {game_name} (from input: {game_name_input}) with difficulty: {difficulty}")

            if game_name == "snake":
                html = generate_snake_html(difficulty, "medium")
            elif game_name == "space-impact":
                html = generate_space_impact_html()
            elif game_name == "tic-tac-toe":
                html = generate_tic_tac_toe_html()
            elif game_name == "breakout":
                html = generate_breakout_html()
            elif game_name == "2048":
                html = generate_2048_html()
            elif game_name == "memory":
                html = generate_memory_html()
            else:
                html = generate_remaining_games(game_name)

            return [TextContent(type="text", text=html)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    logger.info("Starting Game Hub MCP Server with 15 games")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
