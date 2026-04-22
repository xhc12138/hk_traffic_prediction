d3.csv('https://docs.google.com/spreadsheets/d/1cBn1WwKYGBYxz_PTd3Q7e7TIWpHFhSpe6Gxq9k9YqtU/pub?output=csv',(error,raw)=>{
  console.log(error,raw)
  var factor = 1;
  var xKey = 'x_projection';
  var yKey = 'y_projection';
  var viewportPadding = 60;
  var zoomTransform = d3.zoomIdentity;

  var svgRoot = d3.select('#viz');
  var viewport = svgRoot.append('g');

  var xValues = raw.map(d => Number(d[xKey]) * factor).filter(Number.isFinite);
  var yValues = raw.map(d => Number(d[yKey]) * factor).filter(Number.isFinite);
  var minX = d3.min(xValues);
  var maxX = d3.max(xValues);
  var minY = d3.min(yValues);
  var maxY = d3.max(yValues);
  var viewX = minX - viewportPadding;
  var viewY = minY - viewportPadding;
  var viewWidth = (maxX - minX) + viewportPadding * 2;
  var viewHeight = (maxY - minY) + viewportPadding * 2;

  svgRoot
    .attr('viewBox', [viewX, viewY, viewWidth, viewHeight].join(' '))
    .attr('preserveAspectRatio', 'xMidYMid meet');

  svgRoot
    .call(
      d3.zoom()
        .scaleExtent([0.4, 10])
        .on('zoom', () => {
          zoomTransform = d3.event.transform;
          viewport.attr('transform', zoomTransform);
        })
    )
    .on('dblclick.zoom', null);

  viewport
    .append('image')
    .attr('xlink:href', 'mtr.jpg')
    .attr('x', viewX)
    .attr('y', viewY)
    .attr('width', viewWidth)
    .attr('height', viewHeight)
    .attr('preserveAspectRatio', 'none');

  viewport.selectAll('circle')
    .data(raw)
    .enter()
    .append('circle')
      .attr('cx',d=>Number(d[xKey])*factor)
      .attr('cy',d=>Number(d[yKey])*factor)
      .attr('r',5)
      .attr('fill','black')
      .attr('stroke',d=>d.color?d.color:'black')
    .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));


function dragstarted(d) {
  if (d3.event.sourceEvent) {
    d3.event.sourceEvent.stopPropagation();
  }
  d3.select(this).raise().classed("active", true);
}

function dragged(d) {
  var pointer = d3.mouse(svgRoot.node());
  var projected = zoomTransform.invert(pointer);
  d[xKey] = projected[0] / factor;
  d[yKey] = projected[1] / factor;
  d3.select(this).attr("cx", projected[0]).attr("cy", projected[1]);
}

function dragended(d) {
  d3.select(this).classed("active", false);
  console.log(raw.map(d=>{return {x:Number(d[xKey]),y:Number(d[yKey])}}))
}

  function transition(){
    d3.selectAll('circle')
      .transition()
      .duration(4000)
      .attr('cx',d=>d.x_real*factor)
      .attr('cy',d=>d.y_real*factor)
      .on('end',transition2)
  }


  function transition2(){
    d3.selectAll('circle')
      .transition()
      .duration(4000)
      .attr('cx',d=>d.x_projection*factor)
      .attr('cy',d=>d.y_projection*factor)
      .on('end',transition)
  }

  // transition();
})