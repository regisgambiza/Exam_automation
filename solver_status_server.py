from flask import Flask, render_template_string, jsonify
import json
import os

app = Flask(__name__)

STATE_FILE = "solver_state.json"
LOG_FILE = "solver.log"

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Exam Solver Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { padding: 20px; background: #f8f9fa; }
    .card { margin-bottom: 20px; }
    pre {
      max-height: 250px;
      overflow-y: auto;
      background: #212529;
      color: #eee;
      padding: 10px;
      border-radius: 5px;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <h1 class="mb-4">Adaptive Exam Solver Dashboard</h1>

  <div class="row">
    <div class="col-md-3">
      <div class="card text-bg-primary">
        <div class="card-body">
          <h5 class="card-title">Total Attempts</h5>
          <p class="card-text fs-3" id="total-attempts">0</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-success">
        <div class="card-body">
          <h5 class="card-title">Best Score</h5>
          <p class="card-text fs-3" id="best-score">0 / 30</p>
          <div class="progress">
            <div id="score-progress" class="progress-bar" role="progressbar" style="width: 0%"></div>
          </div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-info">
        <div class="card-body">
          <h5 class="card-title">Confirmed Answers</h5>
          <p class="card-text fs-3" id="confirmed-answers">0</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-warning">
        <div class="card-body">
          <h5 class="card-title">Guessed Answers</h5>
          <p class="card-text fs-3" id="guessed-answers">0</p>
        </div>
      </div>
    </div>
  </div>

  <h3>Recent Attempts</h3>
  <div class="table-responsive">
    <table class="table table-striped table-hover align-middle">
      <thead>
        <tr>
          <th>#</th>
          <th>Score</th>
          <th>Changed Indices</th>
          <th>Answers (summary)</th>
        </tr>
      </thead>
      <tbody id="recent-attempts-body"></tbody>
    </table>
  </div>

  <h3>Score Over Time</h3>
  <canvas id="scoreChart" height="100"></canvas>

  <h3>Recent Logs</h3>
  <pre id="log-content">Loading logs...</pre>

  <script>
    const refreshInterval = 5000; // 5 seconds
    let scoreChart;

    function summarizeAnswers(answers) {
      if (!answers) return "";
      return answers.slice(0, 10).join(", ") + (answers.length > 10 ? " ..." : "");
    }

    function updateDashboard(data) {
      document.getElementById("total-attempts").textContent = data.attempts;
      document.getElementById("best-score").textContent = `${data.best_score} / ${data.total_questions}`;
      const progressPercent = (data.best_score / data.total_questions) * 100;
      const progressBar = document.getElementById("score-progress");
      progressBar.style.width = progressPercent + "%";
      progressBar.textContent = Math.round(progressPercent) + "%";

      document.getElementById("confirmed-answers").textContent = data.confirmed;
      document.getElementById("guessed-answers").textContent = data.guessed;

      const tbody = document.getElementById("recent-attempts-body");
      tbody.innerHTML = "";
      data.recent_attempts.forEach((att, i) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${data.attempts - data.recent_attempts.length + i + 1}</td>
          <td>${att.score}</td>
          <td>${att.changed.length ? att.changed.join(", ") : "-"}</td>
          <td>${summarizeAnswers(att.answers)}</td>
        `;
        tbody.appendChild(row);
      });

      const scores = data.all_scores;
      const labels = scores.map((_, i) => `#${i + 1}`);

      if (!scoreChart) {
        const ctx = document.getElementById("scoreChart").getContext("2d");
        scoreChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Score',
              data: scores,
              borderColor: 'rgba(75, 192, 192, 1)',
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              fill: true,
              tension: 0.3,
              pointRadius: 5,
              pointHoverRadius: 8,
              borderWidth: 2
            }]
          },
          options: {
            responsive: true,
            scales: {
              y: {
                min: 0,
                max: data.total_questions,
                ticks: { stepSize: 1 }
              }
            }
          }
        });
      } else {
        scoreChart.data.labels = labels;
        scoreChart.data.datasets[0].data = scores;
        scoreChart.update();
      }
    }

    function updateLogs(logData) {
      const logElement = document.getElementById("log-content");
      logElement.textContent = logData.logs?.length ? logData.logs.join("") : "No logs available.";
    }

    async function fetchData() {
      try {
        const [stateResp, logsResp] = await Promise.all([
          fetch("/api/state"),
          fetch("/api/logs")
        ]);
        const stateData = await stateResp.json();
        const logsData = await logsResp.json();
        updateDashboard(stateData);
        updateLogs(logsData);
      } catch (e) {
        console.error("Failed to fetch data:", e);
      }
    }

    fetchData();
    setInterval(fetchData, refreshInterval);
  </script>
</body>
</html>
"""

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def load_log_entries(max_lines=30):
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-max_lines:]
    except:
        return []

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/state")
def api_state():
    state = load_state()
    attempts_list = state.get("attempts", [])
    attempts = len(attempts_list)
    best_score = max((att.get("score", 0) for att in attempts_list), default=0)
    total_questions = state.get("num_questions", 30)
    correct_answers = state.get("correct_answers", [None] * total_questions)
    confirmed = sum(1 for ans in correct_answers if ans is not None)
    guessed = sum(1 for ans in correct_answers if ans is None)

    recent_attempts = attempts_list[-10:]
    recent_attempts = [
        {
            "score": att.get("score", 0),
            "changed": att.get("changed_indices", []),
            "answers": att.get("answers", [])
        }
        for att in recent_attempts
    ]

    all_scores = [att.get("score", 0) for att in attempts_list]

    return jsonify({
        "attempts": attempts,
        "best_score": best_score,
        "total_questions": total_questions,
        "confirmed": confirmed,
        "guessed": guessed,
        "recent_attempts": recent_attempts,
        "all_scores": all_scores
    })

@app.route("/api/logs")
def api_logs():
    logs = load_log_entries(30)
    return jsonify({"logs": logs})

if __name__ == "__main__":
    app.run(debug=True)
