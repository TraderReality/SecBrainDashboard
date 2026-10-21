const LOOP_STATION_ICONS = {
1: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
2: '<circle cx="11" cy="11" r="6"/><path d="m16 16 5 5"/>',
3: '<path d="M12 3v18"/><path d="M5 7h14"/><path d="m6 7-3 6h6l-3-6Z"/><path d="m18 7-3 6h6l-3-6Z"/><path d="M8 21h8"/>',
4: '<path d="M9 6h11"/><path d="M9 12h11"/><path d="M9 18h11"/><circle cx="4" cy="6" r=".8" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r=".8" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r=".8" fill="currentColor" stroke="none"/>',
5: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/>',
6: '<path d="M7 3h10"/><path d="M7 21h10"/><path d="M8 3c0 5 3 5 4 9 1-4 4-4 4-9"/><path d="M8 21c0-5 3-5 4-9 1 4 4 4 4 9"/>',
7: '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.7 2.7L16.5 9"/>',
8: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/>',
9: '<path d="M10 13.5 8.5 15a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0"/><path d="m14 10.5 1.5-1.5a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0"/><path d="m8.5 15.5 7-7"/>',
10: '<path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z"/><path d="m8.5 12 2.2 2.2 4.8-4.8"/>',
11: '<rect x="6" y="5" width="12" height="16" rx="1"/><path d="M9 5V3h6v2"/><path d="M9 11h6"/><path d="M9 15h6"/>',
12: '<path d="m3 11 18-8-6.5 18-3.1-7.1z"/><path d="m11.9 13.9 4.6-4.6"/>'
};


const LOOP_STATION_METADATA = {
1: { rule: "AGENTS.md §1.1", skill: "vault-first" },
2: { rule: "AGENTS.md §1.1", skill: "vault-first" },
3: { rule: "AGENTS.md §1.1", skill: "vault-first" },
4: { rule: "AGENTS.md §1.1", skill: "vault-first" },
5: { rule: "AGENTS.md §1.1", skill: "proposal-builder" },
6: { rule: "AGENTS.md §1.1", skill: "approval-waiter" },
7: { rule: "AGENTS.md §2.03", skill: "integrator" },
8: { rule: "AGENTS.md §2.09", skill: "indexer" },
9: { rule: "AGENTS.md §2.07", skill: "linker" },
10: { rule: "AGENTS.md §2.10", skill: "auditor" },
11: { rule: "AGENTS.md §2.11", skill: "logger" },
12: { rule: "AGENTS.md §2.12", skill: "reporter" }
};


class LoopRenderer {


constructor(container){

this.container = container;

this.svg = null;

this.brain = null;

this.data = [];

this.ollamaStatus = "offline";

this.ollamaModelConnected = false;

this.ollamaBusy = false;

this.dataSignature = "";

this.autonomousRunning = false;

this.createLayers();

this.startOllamaMonitor();


window.addEventListener(
"resize",
()=>this.render()
);

}



createLayers(){

this.container.innerHTML="";



this.svg =
document.createElementNS(
"http://www.w3.org/2000/svg",
"svg"
);


this.svg.classList.add(
"loop-svg"
);


this.container.appendChild(
this.svg
);



this.brain =
document.createElement(
"img"
);


this.updateBrainGraphic();


this.brain.classList.add(
"brain-core-svg"
);


this.brain.style.pointerEvents = "auto";

this.brain.style.cursor = "pointer";


console.log(
"SECBrain Core Event Ready",
this.brain
);



this.brain.ondblclick = ()=>{

console.log(
"SECBrain Core double click"
);


if(
window.OllamaSettings &&
typeof window.OllamaSettings.open==="function"
){

window.OllamaSettings.open();

}
else{

console.error(
"OllamaSettings nicht geladen"
);

}


};


this.container.appendChild(
this.brain
);


}





async startOllamaMonitor(){

this.refreshOllamaStatus();


setInterval(
()=>this.refreshOllamaStatus(),
5000
);

}



async refreshOllamaStatus(){

const previousStatus = this.ollamaStatus;
const wasModelConnected = this.ollamaModelConnected;

try{

const response =
await fetch(
"/api/ollama/status",
{
method:"GET",
cache:"no-store"
}
);


if(!response.ok){

this.ollamaStatus="offline";

this.ollamaModelConnected = false;

}
else{


const data =
await response.json();


if(data.online && data.model){

this.ollamaStatus="online";

this.ollamaModelConnected = true;

}
else{

this.ollamaStatus="empty";

this.ollamaModelConnected = false;

}


}


}
catch(error){

this.ollamaStatus="offline";

this.ollamaModelConnected = false;

}


this.updateBrainGraphic();

// Unveränderte Poll-Antworten dürfen das SVG nicht neu aufbauen: Sonst
// startet die Ringanimation alle fünf Sekunden neu und wirkt im Leerlauf starr.
if(
previousStatus !== this.ollamaStatus ||
wasModelConnected !== this.ollamaModelConnected
){
this.render();
}

}



updateBrainGraphic(){


if(!this.brain)
return;



if(this.ollamaStatus==="offline"){


this.brain.src =
"/assets/graphics/secbrain-core-offline.svg";


return;

}



if(this.ollamaStatus==="empty"){


this.brain.src =
"/assets/graphics/secbrain-core-warning.svg";


return;

}



if(this.ollamaBusy){


this.brain.src =
"/assets/graphics/secbrain-core-active.svg";


return;

}



this.brain.src =
"/assets/graphics/secbrain-core.png";


}



setData(data){

const nextData = Array.isArray(data) ? data : [];
const nextSignature = JSON.stringify(
nextData.map(station => ({
id: station.id,
name: station.name,
active: Boolean(station.active),
status: station.status
}))
);

if(nextSignature === this.dataSignature){
return;
}

this.data=nextData;
this.dataSignature=nextSignature;

this.render();

}



setAutonomousRunning(running){

this.autonomousRunning = Boolean(running);
this.container.classList.toggle(
"loop-autonomous-running",
this.autonomousRunning
);

}



render(){

if(!this.svg)
return;



const width =
this.container.clientWidth;


const height =
this.container.clientHeight;



if(width < 10 || height < 10)
return;



this.svg.innerHTML="";



this.svg.setAttribute(
"viewBox",
`0 0 ${width} ${height}`
);



const cx =
width / 2;


const cy =
height / 2;



const base =
Math.min(
width,
height
);



const radiusY =
base * 0.37;



const radiusX =
radiusY;



this.drawOrbit(
cx,
cy,
radiusX,
radiusY
);


this.drawCenterLoop(
cx,
cy,
base
);



const count =
this.data.length;



const nodeRadius =
Math.max(
26,
Math.min(
34,
base * 0.05
)
);



this.data.forEach(
(station,index)=>{


const angle =
(
index *
360 /
count
-
90
)
*
Math.PI /
180;



const x =
cx +
radiusX *
Math.cos(angle);



const y =
cy +
radiusY *
Math.sin(angle);



this.drawStation(
station,
x,
y,
nodeRadius,
angle
);


});



this.positionBrain(
cx,
cy
);



}




positionBrain(cx,cy){

this.brain.style.left =
cx+"px";


this.brain.style.top =
cy+"px";


}




drawOrbit(cx,cy,rx,ry){


const circle =
document.createElementNS(
"http://www.w3.org/2000/svg",
"ellipse"
);


circle.setAttribute(
"cx",
cx
);


circle.setAttribute(
"cy",
cy
);


circle.setAttribute("rx",rx);
circle.setAttribute("ry",ry);


circle.setAttribute(
"class",
"loop-orbit"
);


this.svg.appendChild(
circle
);


const phases = [
[-105,15,"loop-orbit-ready"],
[15,75,"loop-orbit-attention"],
[75,165,"loop-orbit-ready"],
[165,195,"loop-orbit-review"],
[195,225,"loop-orbit-attention"],
[225,255,"loop-orbit-ready"]
];


phases.forEach(([start,end,className])=>{
const startAngle = start * Math.PI / 180;
const endAngle = end * Math.PI / 180;
const x1 = cx + rx * Math.cos(startAngle);
const y1 = cy + ry * Math.sin(startAngle);
const x2 = cx + rx * Math.cos(endAngle);
const y2 = cy + ry * Math.sin(endAngle);
const arc = document.createElementNS("http://www.w3.org/2000/svg","path");
arc.setAttribute("d",`M ${x1} ${y1} A ${rx} ${ry} 0 0 1 ${x2} ${y2}`);
arc.setAttribute("class",className);
this.svg.appendChild(arc);
});


}



drawCenterLoop(cx,cy,base){


const innerOrbit =
document.createElementNS(
"http://www.w3.org/2000/svg",
"circle"
);


innerOrbit.setAttribute("cx",cx);
innerOrbit.setAttribute("cy",cy);
innerOrbit.setAttribute("r",base * 0.205);
innerOrbit.setAttribute("class","loop-center-orbit");
this.svg.appendChild(innerOrbit);


if(!this.ollamaModelConnected){
return;
}


const defs = document.createElementNS(
"http://www.w3.org/2000/svg","defs"
);
const marker = document.createElementNS(
"http://www.w3.org/2000/svg","marker"
);
marker.setAttribute("id","core-connection-arrowhead");
marker.setAttribute("viewBox","0 0 10 10");
marker.setAttribute("refX","8");
marker.setAttribute("refY","5");
marker.setAttribute("markerWidth","6");
marker.setAttribute("markerHeight","6");
marker.setAttribute("orient","auto");
const arrowhead = document.createElementNS(
"http://www.w3.org/2000/svg","path"
);
arrowhead.setAttribute("d","M 0 0 L 10 5 L 0 10 z");
arrowhead.setAttribute("class","core-connection-arrowhead");
marker.appendChild(arrowhead);
defs.appendChild(marker);
this.svg.appendChild(defs);


const arrows = document.createElementNS(
"http://www.w3.org/2000/svg","g"
);
arrows.classList.add("core-connection-arrows");
arrows.style.setProperty("--core-x",cx + "px");
arrows.style.setProperty("--core-y",cy + "px");
const arrowRadius = base * 0.205;


[[205,18],[25,198]].forEach((range,index)=>{
const start = range[0] * Math.PI / 180;
const end = range[1] * Math.PI / 180;
const x1 = cx + arrowRadius * Math.cos(start);
const y1 = cy + arrowRadius * Math.sin(start);
const x2 = cx + arrowRadius * Math.cos(end);
const y2 = cy + arrowRadius * Math.sin(end);
const arc = document.createElementNS(
"http://www.w3.org/2000/svg","path"
);
arc.setAttribute("d",`M ${x1} ${y1} A ${arrowRadius} ${arrowRadius} 0 0 1 ${x2} ${y2}`);
arc.setAttribute("marker-end","url(#core-connection-arrowhead)");
arc.classList.add("core-connection-arrow","core-connection-arrow-" + index);
arrows.appendChild(arc);
});


this.svg.appendChild(arrows);


}




drawStation(
station,
x,
y,
r,
angle
){


const group =
document.createElementNS(
"http://www.w3.org/2000/svg",
"g"
);


group.classList.add(
"station-node"
);


group.classList.add(
"station-phase-" + this.getStationPhase(station.id)
);



const circle =
document.createElementNS(
"http://www.w3.org/2000/svg",
"circle"
);


circle.setAttribute(
"cx",
x
);


circle.setAttribute(
"cy",
y
);


circle.setAttribute(
"r",
r
);



circle.setAttribute(
"class",
station.active
?
"station-active"
:
"station-normal"
);



const icon =
this.createStationIcon(
station,
x,
y,
r
);



group.appendChild(
circle
);


group.appendChild(
icon
);



this.drawStationNumber(
group,
station,
x,
y,
r
);



this.drawStationLabel(
group,
station,
x,
y,
r,
angle
);



group.onclick=()=>{

document.dispatchEvent(
new CustomEvent(
"station-selected",
{
detail:station
}


)
);

};



this.svg.appendChild(
group
);


}



getStationPhase(stationId){


const id = Number(stationId);


if(id === 5 || id === 6 || id === 11){
return "attention";
}


if(id === 10){
return "review";
}


return "ready";


}



drawStationNumber(group,station,x,y,r){


const badge =
document.createElementNS(
"http://www.w3.org/2000/svg",
"circle"
);


const badgeRadius = Math.max(8,r * 0.22);


const badgeY = y - r - badgeRadius * 0.35;


badge.setAttribute("cx",x);
badge.setAttribute("cy",badgeY);
badge.setAttribute("r",badgeRadius);
badge.classList.add("station-number-badge");


const number =
document.createElementNS(
"http://www.w3.org/2000/svg",
"text"
);


number.setAttribute("x",x);
number.setAttribute("y",badgeY + badgeRadius * 0.35);
number.setAttribute("text-anchor","middle");
number.classList.add("station-number");
number.textContent = Number(station.id).toString().padStart(2,"0");


group.appendChild(badge);
group.appendChild(number);


}



drawStationLabel(group,station,x,y,r,angle){


const labelGroup =
document.createElementNS(
"http://www.w3.org/2000/svg",
"g"
);


const label =
document.createElementNS(
"http://www.w3.org/2000/svg",
"text"
);


const stationId = Number(station.id);
const metadata = LOOP_STATION_METADATA[stationId];
const showMetadata = r >= 30;
const topLabel = stationId === 1;
const bottomLabel = stationId === 7;
const labelSide =
topLabel || bottomLabel
?
1
:
(Math.cos(angle) >= 0 ? 1 : -1);
const labelOffsetY = stationId === 6 ? -18 : 0;
const labelY =
topLabel
?
(y - r - 45)
:
(bottomLabel ? (y + r + 22) : (y + labelOffsetY));
const labelX =
topLabel || bottomLabel
?
x
:
(x + labelSide * (r + (showMetadata ? 18 : 12)));
const labelAnchor =
topLabel || bottomLabel
?
"middle"
:
(labelSide === 1
?
"start"
:
"end");


label.setAttribute("x",labelX);
label.setAttribute("y",showMetadata ? labelY : labelY + 5);
label.setAttribute("text-anchor",labelAnchor);
label.classList.add("station-label");
label.textContent = station.name;


labelGroup.appendChild(label);


if(showMetadata && metadata){


const rule =
document.createElementNS(
"http://www.w3.org/2000/svg",
"text"
);


rule.setAttribute("x",labelX);
rule.setAttribute("y",labelY + 15);
rule.setAttribute("text-anchor",labelAnchor);
rule.classList.add("station-label-rule");
rule.textContent = "Regel: " + metadata.rule;


const skill =
document.createElementNS(
"http://www.w3.org/2000/svg",
"text"
);


skill.setAttribute("x",labelX);
skill.setAttribute("y",labelY + 27);
skill.setAttribute("text-anchor",labelAnchor);
skill.classList.add("station-label-skill");
skill.textContent = "Skill: " + metadata.skill;


labelGroup.appendChild(rule);
labelGroup.appendChild(skill);


}


group.appendChild(labelGroup);


}


createStationIcon(station,x,y,r){


const icon =
document.createElementNS(
"http://www.w3.org/2000/svg",
"svg"
);


// 24px viewBox mit etwas größerer sichtbarer Glyphenfläche,
// damit die Icons im Kreis optisch dieselbe Präsenz wie im Referenzlayout haben.
const iconSize = r * 1.25;


icon.setAttribute("x",x - iconSize / 2);
icon.setAttribute("y",y - iconSize / 2);
icon.setAttribute("width",iconSize);
icon.setAttribute("height",iconSize);
icon.setAttribute("viewBox","0 0 24 24");
icon.setAttribute("preserveAspectRatio","xMidYMid meet");
icon.setAttribute("fill","none");
icon.setAttribute("stroke","currentColor");
icon.setAttribute("stroke-width","1.75");
icon.setAttribute("stroke-linecap","round");
icon.setAttribute("stroke-linejoin","round");
icon.setAttribute("aria-hidden","true");


icon.classList.add(
"station-icon",
station.active
?
"station-icon-active"
:
"station-icon-normal"
);


icon.innerHTML =
LOOP_STATION_ICONS[Number(station.id)] ||
LOOP_STATION_ICONS[1];


return icon;


}



}


window.LoopRenderer =
LoopRenderer;
