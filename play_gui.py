import argparse
import queue
import threading
import tkinter as tk
from tkinter import ttk

from dlgo.goboard import GameState, Move
from dlgo.gotypes import Player, Point
from dlgo.scoring import compute_game_result


def create_agent(name):
    if name == "random":
        from agents.random_agent import RandomAgent

        return RandomAgent()

    if name == "mcts":
        from agents.mcts_agent import MCTSAgent

        return MCTSAgent(num_rounds=300, max_seconds=1.0)

    if name == "mcts_prototype":
        from agents.mcts_prototype_agent import MCTSAgent

        return MCTSAgent(num_rounds=300, max_seconds=1.0)

    if name == "minimax":
        from agents.minimax_agent import MinimaxAgent

        return MinimaxAgent()

    raise ValueError(f"Unsupported agent: {name}")


class GoGUIApp:
    AI_OPTIONS = ("random", "mcts", "mcts_prototype", "minimax")
    SIZE_OPTIONS = ("5", "9", "13")
    HUMAN_OPTIONS = ("black", "white")

    def __init__(self, board_size=5, ai_name="mcts", human_color="black"):
        self.root = tk.Tk()
        self.root.title("Go Human vs AI")

        self.size_var = tk.StringVar(value=str(board_size))
        self.ai_var = tk.StringVar(value=ai_name)
        self.human_var = tk.StringVar(value=human_color)

        self.turn_var = tk.StringVar(value="")
        self.capture_var = tk.StringVar(value="")
        self.last_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self.margin = 40
        self.cell = 50

        self.game_state = None
        self.black_captures = 0
        self.white_captures = 0
        self.last_action_text = ""
        self.history = []

        self.ai_queue = queue.Queue()
        self.ai_thinking = False
        self.ai_request_id = 0

        self._build_layout()
        self.start_new_game()

    def _build_layout(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        board_frame = ttk.Frame(outer)
        board_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(board_frame, bg="#D9A45A", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        side = ttk.Frame(outer, padding=(12, 0, 0, 0))
        side.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(side, text="Human color").pack(anchor="w")
        ttk.Combobox(
            side,
            textvariable=self.human_var,
            values=self.HUMAN_OPTIONS,
            state="readonly",
            width=14,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(side, text="AI agent").pack(anchor="w")
        ttk.Combobox(
            side,
            textvariable=self.ai_var,
            values=self.AI_OPTIONS,
            state="readonly",
            width=14,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(side, text="Board size").pack(anchor="w")
        ttk.Combobox(
            side,
            textvariable=self.size_var,
            values=self.SIZE_OPTIONS,
            state="readonly",
            width=14,
        ).pack(anchor="w", pady=(0, 12))

        ttk.Button(side, text="New Game", command=self.start_new_game).pack(
            fill=tk.X, pady=2
        )
        ttk.Button(side, text="Undo", command=self.undo_turn).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Pass", command=self.human_pass).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Resign", command=self.human_resign).pack(fill=tk.X, pady=2)

        ttk.Separator(side, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(side, textvariable=self.turn_var).pack(anchor="w", pady=2)
        ttk.Label(side, textvariable=self.capture_var).pack(anchor="w", pady=2)
        ttk.Label(side, textvariable=self.last_var, wraplength=220).pack(anchor="w", pady=2)

        ttk.Separator(side, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(side, textvariable=self.status_var, wraplength=220).pack(anchor="w", pady=2)

    def run(self):
        self.root.mainloop()

    def _human_player(self):
        return Player.black if self.human_var.get() == "black" else Player.white

    def _ai_player(self):
        return self._human_player().other

    def _board_size(self):
        value = self.size_var.get().strip()
        try:
            size = int(value)
        except ValueError:
            size = 5
        return max(2, size)

    def _cancel_pending_ai(self):
        self.ai_request_id += 1
        self.ai_thinking = False

    def start_new_game(self):
        self._cancel_pending_ai()

        size = self._board_size()
        self.game_state = GameState.new_game(size)
        self.black_captures = 0
        self.white_captures = 0
        self.last_action_text = "New game started."
        self.history = [
            (self.game_state, self.black_captures, self.white_captures, self.last_action_text)
        ]

        self._set_status("Click an intersection to play.")
        self._refresh_ui()

        if self.game_state.next_player == self._ai_player():
            self._start_ai_turn()

    def undo_turn(self):
        if len(self.history) <= 1:
            self._set_status("No move to undo.")
            return

        self._cancel_pending_ai()
        self.history.pop()

        if len(self.history) > 1 and self.history[-1][0].next_player == self._ai_player():
            self.history.pop()

        state, black_caps, white_caps, last_text = self.history[-1]
        self.game_state = state
        self.black_captures = black_caps
        self.white_captures = white_caps
        self.last_action_text = last_text

        self._set_status("Undo completed.")
        self._refresh_ui()

    def human_pass(self):
        if not self._human_can_move():
            return
        self._apply_move(Move.pass_turn(), "Human")

    def human_resign(self):
        if not self._human_can_move():
            return
        self._apply_move(Move.resign(), "Human")

    def on_canvas_click(self, event):
        if not self._human_can_move():
            return

        point = self._event_to_point(event.x, event.y)
        if point is None:
            return

        move = Move.play(point)
        if not self.game_state.is_valid_move(move):
            self._set_status("Illegal move. Try another point.")
            return

        self._apply_move(move, "Human")

    def _human_can_move(self):
        if self.game_state is None:
            return False
        if self.ai_thinking:
            self._set_status("AI is thinking. Please wait.")
            return False
        if self.game_state.is_over():
            self._set_status("Game is over. Start a new game.")
            return False
        if self.game_state.next_player != self._human_player():
            self._set_status("It is AI's turn.")
            return False
        return True

    def _start_ai_turn(self):
        if self.game_state.is_over():
            return
        if self.game_state.next_player != self._ai_player():
            return
        if self.ai_thinking:
            return

        request_id = self.ai_request_id + 1
        self.ai_request_id = request_id
        self.ai_thinking = True

        state_for_ai = self.game_state
        ai_name = self.ai_var.get()
        self._set_status(f"AI ({ai_name}) is thinking...")

        thread = threading.Thread(
            target=self._compute_ai_move_worker,
            args=(request_id, state_for_ai, ai_name),
            daemon=True,
        )
        thread.start()

        self.root.after(80, self._poll_ai_result)

    def _compute_ai_move_worker(self, request_id, state_snapshot, ai_name):
        try:
            agent = create_agent(ai_name)
            move = agent.select_move(state_snapshot)
            self.ai_queue.put((request_id, move, None))
        except Exception as exc:
            self.ai_queue.put((request_id, None, str(exc)))

    def _poll_ai_result(self):
        if not self.ai_thinking:
            return

        try:
            request_id, move, error = self.ai_queue.get_nowait()
        except queue.Empty:
            self.root.after(80, self._poll_ai_result)
            return

        if request_id != self.ai_request_id:
            self.root.after(20, self._poll_ai_result)
            return

        self.ai_thinking = False

        if error is not None:
            self._set_status(f"AI failed: {error}")
            return

        if move is None:
            move = Move.pass_turn()

        if self.game_state.is_over() or self.game_state.next_player != self._ai_player():
            return

        self._apply_move(move, "AI")

    def _apply_move(self, move, actor):
        before_black, before_white = self._count_stones(self.game_state.board)
        mover = self.game_state.next_player

        try:
            new_state = self.game_state.apply_move(move)
        except Exception as exc:
            self._set_status(f"Move failed: {exc}")
            return

        after_black, after_white = self._count_stones(new_state.board)

        if move.is_play:
            if mover == Player.black:
                captured = max(0, before_white - after_white)
                self.black_captures += captured
            else:
                captured = max(0, before_black - after_black)
                self.white_captures += captured
        else:
            captured = 0

        text = f"{actor} played {self._format_move(move)}"
        if captured > 0:
            text += f" and captured {captured}"

        self.game_state = new_state
        self.last_action_text = text
        self.history.append(
            (self.game_state, self.black_captures, self.white_captures, self.last_action_text)
        )

        self._refresh_ui()

        if not self.game_state.is_over() and self.game_state.next_player == self._ai_player():
            self._start_ai_turn()

    def _refresh_ui(self):
        self._resize_canvas_for_board()
        self._draw_board()
        self._update_info_panel()

    def _resize_canvas_for_board(self):
        size = self.game_state.board.num_rows
        self.cell = max(30, min(60, int(520 / max(1, size - 1))))
        board_px = self.cell * (size - 1)
        side = board_px + self.margin * 2
        self.canvas.config(width=side, height=side)

    def _draw_board(self):
        board = self.game_state.board
        size = board.num_rows

        self.canvas.delete("all")

        side = self.margin * 2 + self.cell * (size - 1)
        self.canvas.create_rectangle(0, 0, side, side, fill="#D9A45A", outline="#D9A45A")

        for i in range(size):
            x = self.margin + i * self.cell
            y = self.margin + i * self.cell
            self.canvas.create_line(self.margin, y, side - self.margin, y, width=1)
            self.canvas.create_line(x, self.margin, x, side - self.margin, width=1)

            label = str(i + 1)
            self.canvas.create_text(self.margin - 18, y, text=label)
            self.canvas.create_text(x, self.margin - 18, text=label)

        last_point = None
        if self.game_state.last_move is not None and self.game_state.last_move.is_play:
            last_point = self.game_state.last_move.point

        stone_radius = self.cell * 0.42
        marker_radius = max(2, int(self.cell * 0.08))

        for row in range(1, size + 1):
            for col in range(1, size + 1):
                stone = board.get(Point(row, col))
                if stone is None:
                    continue

                x, y = self._point_to_xy(Point(row, col))
                fill = "#111111" if stone == Player.black else "#F8F8F8"
                outline = "#111111"

                self.canvas.create_oval(
                    x - stone_radius,
                    y - stone_radius,
                    x + stone_radius,
                    y + stone_radius,
                    fill=fill,
                    outline=outline,
                    width=1,
                )

                if last_point is not None and row == last_point.row and col == last_point.col:
                    marker_color = "#FF3B30" if stone == Player.black else "#0A0A0A"
                    self.canvas.create_oval(
                        x - marker_radius,
                        y - marker_radius,
                        x + marker_radius,
                        y + marker_radius,
                        fill=marker_color,
                        outline=marker_color,
                    )

    def _update_info_panel(self):
        if self.game_state.is_over():
            winner = self.game_state.winner()
            result = compute_game_result(self.game_state)
            if self.game_state.last_move is not None and self.game_state.last_move.is_resign:
                summary = f"Game over. Winner: {self._player_name(winner)} by resignation."
            else:
                summary = f"Game over. Winner: {self._player_name(winner)} ({result})."
            self.turn_var.set(summary)
        else:
            next_player = self.game_state.next_player
            role = "Human" if next_player == self._human_player() else "AI"
            self.turn_var.set(f"Turn: {self._player_name(next_player)} ({role})")

        self.capture_var.set(
            f"Captures - Black: {self.black_captures} | White: {self.white_captures}"
        )
        self.last_var.set(f"Last: {self.last_action_text}")

    def _set_status(self, text):
        self.status_var.set(text)

    def _event_to_point(self, x, y):
        board = self.game_state.board

        col_float = (x - self.margin) / self.cell
        row_float = (y - self.margin) / self.cell

        col = int(round(col_float)) + 1
        row = int(round(row_float)) + 1

        if not (1 <= row <= board.num_rows and 1 <= col <= board.num_cols):
            return None

        return Point(row=row, col=col)

    def _point_to_xy(self, point):
        x = self.margin + (point.col - 1) * self.cell
        y = self.margin + (point.row - 1) * self.cell
        return x, y

    @staticmethod
    def _count_stones(board):
        black = 0
        white = 0
        for row in range(1, board.num_rows + 1):
            for col in range(1, board.num_cols + 1):
                stone = board.get(Point(row, col))
                if stone == Player.black:
                    black += 1
                elif stone == Player.white:
                    white += 1
        return black, white

    @staticmethod
    def _format_move(move):
        if move.is_pass:
            return "pass"
        if move.is_resign:
            return "resign"
        return f"({move.point.row}, {move.point.col})"

    @staticmethod
    def _player_name(player):
        if player == Player.black:
            return "Black"
        if player == Player.white:
            return "White"
        return "Unknown"


def parse_args():
    parser = argparse.ArgumentParser(description="Go GUI: Human vs AI")
    parser.add_argument("--size", type=int, default=5, help="Board size, e.g. 5/9/13")
    parser.add_argument(
        "--ai",
        choices=GoGUIApp.AI_OPTIONS,
        default="mcts",
        help="AI agent",
    )
    parser.add_argument(
        "--human",
        choices=GoGUIApp.HUMAN_OPTIONS,
        default="black",
        help="Human color",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    app = GoGUIApp(board_size=args.size, ai_name=args.ai, human_color=args.human)
    app.run()


if __name__ == "__main__":
    main()
