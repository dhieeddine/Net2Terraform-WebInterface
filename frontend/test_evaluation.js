/**
 * Test & Evaluation Frontend Logic
 * Handles RAG and LLM result quality assessment
 */

let testCases = [];
let currentTestName = null;
let evaluationSummary = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Test Evaluation page loaded');
    await loadTestCases();
    await updateSummary();
});

/**
 * Load all available test cases from backend
 */
async function loadTestCases() {
    try {
        const response = await fetch('/api/test/cases');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        testCases = await response.json();
        console.log(`Loaded ${testCases.length} test cases`);
        
        renderTestList();
        
        // Select first test by default
        if (testCases.length > 0) {
            selectTest(testCases[0].name);
        }
    } catch (error) {
        console.error('Failed to load test cases:', error);
        document.getElementById('testCasesList').innerHTML = 
            '<div style="color: red; padding: 10px;">Failed to load test cases</div>';
    }
}

/**
 * Render the test cases list
 */
function renderTestList() {
    const listContainer = document.getElementById('testCasesList');
    listContainer.innerHTML = '';
    
    testCases.forEach(test => {
        const testItem = document.createElement('div');
        testItem.className = 'test-item';
        testItem.onclick = () => selectTest(test.name);
        
        testItem.innerHTML = `
            <div class="test-item-name">${test.name}</div>
            <div class="test-item-desc">${test.description || 'No description'}</div>
        `;
        
        listContainer.appendChild(testItem);
    });
}

/**
 * Select and display a test case
 */
function selectTest(testName) {
    currentTestName = testName;
    
    // Update active state in list
    document.querySelectorAll('.test-item').forEach(item => {
        item.classList.remove('active');
    });
    event.target.closest('.test-item')?.classList.add('active');
    
    // Find the test case
    const test = testCases.find(t => t.name === testName);
    if (!test) return;
    
    // Update UI
    document.getElementById('testTitle').textContent = test.name;
    document.getElementById('testDescription').textContent = test.description || 'No description';
    document.getElementById('testPrompt').textContent = test.prompt.trim();
    
    // Render expected properties
    const propsContainer = document.getElementById('expectedProperties');
    propsContainer.innerHTML = '';
    
    const props = test.expected_properties || {};
    for (const [key, value] of Object.entries(props)) {
        const propItem = document.createElement('div');
        propItem.className = 'property-item';
        propItem.innerHTML = `
            <span class="property-key">${key}:</span>
            <span class="property-value">${formatValue(value)}</span>
        `;
        propsContainer.appendChild(propItem);
    }
    
    // Show test detail and hide results
    document.getElementById('testDetail').style.display = 'block';
    document.getElementById('resultsContainer').classList.remove('active');
    
    // Update button state
    document.getElementById('runTestBtn').disabled = false;
    document.getElementById('runTestBtn').textContent = 'Run Test';
}

/**
 * Run the current selected test
 */
async function runCurrentTest() {
    if (!currentTestName) return;
    
    const runBtn = document.getElementById('runTestBtn');
    const originalText = runBtn.textContent;
    
    try {
        // Show loading state
        runBtn.disabled = true;
        runBtn.innerHTML = '<span class="loading-spinner"></span>Running...';
        
        console.log(`Running test: ${currentTestName}`);
        
        const response = await fetch(`/api/test/run/${currentTestName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                test_name: currentTestName
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }
        
        const result = await response.json();
        
        // Display results
        displayResults(result);
        
        // Update summary
        await updateSummary();
        
    } catch (error) {
        console.error('Test execution failed:', error);
        showError(`Test execution failed: ${error.message}`);
    } finally {
        runBtn.disabled = false;
        runBtn.textContent = originalText;
    }
}

/**
 * Display test results
 */
function displayResults(result) {
    const container = document.getElementById('resultsContainer');
    container.classList.add('active');
    
    // Status
    const statusEl = document.getElementById('resultStatus');
    const passed = result.passed;
    statusEl.className = `result-status ${passed ? 'passed' : 'failed'}`;
    statusEl.textContent = passed ? '✓ PASSED' : '✗ FAILED';
    
    // Checks grid
    const checksGrid = document.getElementById('checksGrid');
    checksGrid.innerHTML = '';
    
    for (const [checkName, checkResult] of Object.entries(result.checks)) {
        const checkItem = document.createElement('div');
        checkItem.className = `check-item ${checkResult ? 'passed' : 'failed'}`;
        
        const icon = checkResult ? '✓' : '✗';
        checkItem.innerHTML = `
            <div class="check-name">${icon} ${formatCheckName(checkName)}</div>
            <div class="check-result">${checkResult ? 'Passed' : 'Failed'}</div>
        `;
        
        checksGrid.appendChild(checkItem);
    }
    
    // Issues
    const issuesSection = document.getElementById('issuesSection');
    if (result.issues && result.issues.length > 0) {
        issuesSection.classList.add('active');
        const issuesList = document.getElementById('issuesList');
        issuesList.innerHTML = '';
        
        result.issues.forEach(issue => {
            const issueItem = document.createElement('div');
            issueItem.className = 'issue-item';
            issueItem.textContent = issue;
            issuesList.appendChild(issueItem);
        });
    } else {
        issuesSection.classList.remove('active');
    }
    
    // Metrics
    const metricsGrid = document.getElementById('metricsGrid');
    metricsGrid.innerHTML = '';
    
    if (result.metrics && Object.keys(result.metrics).length > 0) {
        for (const [metricName, metricValue] of Object.entries(result.metrics)) {
            const metricCard = document.createElement('div');
            metricCard.className = 'metric-card';
            
            let formattedValue = formatValue(metricValue);
            if (typeof metricValue === 'number' && metricValue < 1 && metricValue >= 0) {
                formattedValue = (metricValue * 100).toFixed(1) + '%';
            }
            
            metricCard.innerHTML = `
                <div class="metric-label">${formatCheckName(metricName)}</div>
                <div class="metric-value">${formattedValue}</div>
            `;
            
            metricsGrid.appendChild(metricCard);
        }
    }
}

/**
 * Update evaluation summary from backend
 */
async function updateSummary() {
    try {
        const response = await fetch('/api/test/summary');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        evaluationSummary = await response.json();
        
        // Update summary display
        document.getElementById('totalEvals').textContent = evaluationSummary.total_evals;
        document.getElementById('passedEvals').textContent = evaluationSummary.passed;
        document.getElementById('failedEvals').textContent = evaluationSummary.failed;
        
        const passRate = evaluationSummary.pass_rate * 100;
        document.getElementById('passRate').textContent = passRate.toFixed(1) + '%';
        
    } catch (error) {
        console.error('Failed to update summary:', error);
    }
}

/**
 * Reset evaluation history
 */
async function resetEvaluation() {
    if (!confirm('Are you sure you want to clear evaluation history?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/test/reset', {
            method: 'POST'
        });
        
        if (response.ok) {
            document.getElementById('resultsContainer').classList.remove('active');
            await updateSummary();
            alert('Evaluation history cleared');
        }
    } catch (error) {
        console.error('Failed to reset evaluation:', error);
        showError('Failed to reset evaluation history');
    }
}

/**
 * Format check name for display
 */
function formatCheckName(name) {
    return name
        .replace(/_/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Format value for display
 */
function formatValue(value) {
    if (typeof value === 'boolean') {
        return value ? 'Yes' : 'No';
    }
    if (typeof value === 'number') {
        if (Number.isInteger(value)) {
            return value.toString();
        }
        return value.toFixed(2);
    }
    return String(value);
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('resultsContainer');
    container.classList.add('active');
    
    const statusEl = document.getElementById('resultStatus');
    statusEl.className = 'result-status failed';
    statusEl.textContent = '✗ ERROR';
    
    const checksGrid = document.getElementById('checksGrid');
    checksGrid.innerHTML = `<div style="grid-column: 1/-1; color: red; padding: 10px;">${message}</div>`;
}
