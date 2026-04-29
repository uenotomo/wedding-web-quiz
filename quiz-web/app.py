from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import time
import socket
import json
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

with open("questions.json", encoding="utf-8") as f:
    questions = json.load(f)

# ステージ管理
stage = 0  # 0=QR, 1=感謝祭, 2=練習ページ, 3=練習問題, 4=本問題ページ, 5〜9=本番1〜5問, 10=総合ランキング

current_question_index = -1
start_time = None
answers = []
answered_users = set()

# 本番5問の累積スコア
scores = {}

@app.route("/")
def index():
    # クラウドではローカルIPは不要なのでテンプレートに渡さない
    return render_template("index.html")

@app.route("/admin")
def admin():
    # クラウドではローカルIPは不要なのでテンプレートに渡さない
    return render_template("admin.html")

@socketio.on("next_stage")
def next_stage():
    global stage, current_question_index, start_time, answers, answered_users

    stage += 1

    # ステージに応じて動作
    if stage in [1, 2, 4]:
        # 感謝祭 / 練習ページ / 本問題ページ
        emit("show_stage", {"stage": stage}, broadcast=True)

    elif stage == 3:
        # 練習問題を出題
        current_question_index = 0
        q = questions[current_question_index]
        start_time = time.time()
        answers = []
        answered_users = set()
        emit("show_question", {"stage": stage, "text": q["text"], "choices": q["choices"]}, broadcast=True)

    elif stage in [5, 6, 7, 8, 9]:
        # 本番問題（1〜5問）
        current_question_index = stage - 4  # 本番1問目は questions[1]
        q = questions[current_question_index]
        start_time = time.time()
        answers = []
        answered_users = set()
        emit("show_question", {"stage": stage, "text": q["text"], "choices": q["choices"]}, broadcast=True)

    elif stage == 10:
        # 総合ランキング
        final_list = []
        for name, v in scores.items():
            final_list.append({
                "name": name,
                "points": v["points"],
                "time": v["time"]
            })

        final_list.sort(key=lambda x: (-x["points"], x["time"]))
        emit("final_ranking", final_list[:10], broadcast=True)

@socketio.on("answer")
def handle_answer(data):
    global start_time, answers, answered_users

    name = data["name"]
    choice = data["choice"]

    if name in answered_users:
        return

    t = time.time() - start_time
    correct = (choice == questions[current_question_index]["correct"])

    # choice も保存（投票数集計用）
    answers.append({"name": name, "time": t, "correct": correct, "choice": choice})
    answered_users.add(name)

@socketio.on("finish_quiz")
def finish_quiz():
    # ここでは投票数だけを集計して送る（正解はまだ送らない）
    vote_count = {}
    for key in questions[current_question_index]["choices"].keys():
        vote_count[key] = 0

    for a in answers:
        ch = a["choice"]
        if ch in vote_count:
            vote_count[ch] += 1

    emit("vote_result", vote_count, broadcast=True)

@socketio.on("show_correct")
def show_correct():
    # 結果ボタンが押されたときにだけ正解を送る
    correct_choice = questions[current_question_index]["correct"]
    emit("correct_choice", {"correct_choice": correct_choice}, broadcast=True)

@socketio.on("finish_quiz_after_vote")
def finish_quiz_after_vote():
    global scores

    # 正解者だけを抽出してタイム順にソート
    correct_list = [a for a in answers if a["correct"]]
    correct_list.sort(key=lambda x: x["time"])

    emit("ranking", correct_list, broadcast=True)

    # 練習問題はポイントなし
    if stage == 3:
        return

    # 本番問題はポイント加算
    for idx, a in enumerate(correct_list):
        rank = idx + 1
        if rank == 1:
            pt = 2.0
        elif rank == 2:
            pt = 1.5
        elif rank == 3:
            pt = 1.2
        else:
            pt = 1.0

        name = a["name"]
        time_used = a["time"]

        if name not in scores:
            scores[name] = {"points": 0.0, "time": 0.0}

        scores[name]["points"] += pt
        scores[name]["time"] += time_used

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)

