// State polling data - paste your CSV data here as JavaScript object
const stateData = [
    {state: "Alabama", democracy_world: -2.1, israel_aid: 6.4, ukraine_aid: 26.8, argentina_aid: -39.2, obamacare: 18.7, trump_overall: 4.2, trump_jobs: 1.7, trump_inflation: -4.8, trump_immigration: 12.4, trump_foreign: 1.2, generic_ballot: -8.7},
    {state: "Alaska", democracy_world: 1.8, israel_aid: 4.2, ukraine_aid: 29.7, argentina_aid: -37.4, obamacare: 21.4, trump_overall: -1.8, trump_jobs: -4.2, trump_inflation: -9.7, trump_immigration: 8.7, trump_foreign: -2.8, generic_ballot: -4.2},
    {state: "Arizona", democracy_world: 2.7, israel_aid: -11.8, ukraine_aid: 34.2, argentina_aid: -37.4, obamacare: 27.3, trump_overall: -14.1, trump_jobs: -15.7, trump_inflation: -32.7, trump_immigration: 4.7, trump_foreign: -12.7, generic_ballot: 3.4},
    // ... include all 51 states/territories from the CSV
];

let currentMetric = 'democracy_world';

function initializeMap() {
    updateMap(currentMetric);
    
    document.getElementById('metric-select').addEventListener('change', function() {
        currentMetric = this.value;
        updateMap(currentMetric);
    });
}

function updateMap(metric) {
    const metricTitles = {
        'democracy_world': 'Promote Democracy Worldwide',
        'israel_aid': 'Military Aid to Israel',
        'ukraine_aid': 'Military Aid to Ukraine',
        'argentina_aid': 'US Aid to Argentina',
        'obamacare': 'Obamacare Approval',
        'trump_overall': 'Trump Overall Approval',
        'trump_jobs': 'Trump Jobs/Economy Approval',
        'trump_inflation': 'Trump Inflation Approval',
        'trump_immigration': 'Trump Immigration Approval',
        'trump_foreign': 'Trump Foreign Policy Approval',
        'generic_ballot': 'Generic Congressional Ballot'
    };
    
    const data = [{
        type: 'choropleth',
        locations: stateData.map(d => d.state),
        z: stateData.map(d => d[metric]),
        locationmode: 'USA-states',
        text: stateData.map(d => `${d.state}<br>${metricTitles[metric]}: ${d[metric].toFixed(1)}%`),
        hoverinfo: 'text',
        colorscale: [
            [0, 'rgb(178, 24, 43)'],    // Strong Republican/Against
            [0.25, 'rgb(214, 96, 77)'], // Lean Republican/Against
            [0.5, 'rgb(244, 244, 244)'], // Neutral
            [0.75, 'rgb(67, 147, 195)'], // Lean Democratic/Support
            [1, 'rgb(33, 102, 172)']    // Strong Democratic/Support
        ],
        colorbar: {
            title: 'Margin (%)',
            titleside: 'right'
        },
        zmin: -60,
        zmax: 60
    }];
    
    const layout = {
        title: `${metricTitles[metric]}<br><sub>Positive = Democratic/Support, Negative = Republican/Oppose</sub>`,
        geo: {
            scope: 'usa',
            projection: { type: 'albers usa' },
            showlakes: true,
            lakecolor: 'rgb(255, 255, 255)'
        },
        height: 500
    };
    
    Plotly.newPlot('map', data, layout, { responsive: true });
    
    // Update state table
    updateStateTable(metric);
}

function updateStateTable(metric) {
    const sortedStates = [...stateData].sort((a, b) => b[metric] - a[metric]);
    const tableBody = document.getElementById('state-table-body');
    tableBody.innerHTML = '';
    
    sortedStates.forEach((state, index) => {
        const row = document.createElement('tr');
        const value = state[metric];
        const color = value > 0 ? '#2166ac' : value < 0 ? '#b2182b' : '#777';
        
        row.innerHTML = `
            <td>${state.state}</td>
            <td style="color: ${color}; font-weight: bold">${value > 0 ? '+' : ''}${value.toFixed(1)}%</td>
            <td>${index + 1}</td>
        `;
        tableBody.appendChild(row);
    });
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', initializeMap);