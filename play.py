"""
Simple CLI to run Go agents against each other.

Examples:
    python play.py --agent1 mcts --agent2 random --size 5
    python play.py --agent1 minimax --agent2 mcts --size 5 --games 10
"""

import argparse
import random
import time

from dlgo import GameState, Player, Point
from dlgo.goboard import Move
from dlgo.scoring import compute_game_result


def random_agent(game_state):
    """Pick a random legal move."""
    try:
        from agents.random_agent import RandomAgent

        agent = RandomAgent()
        return agent.select_move(game_state)
    except ImportError:
        moves = game_state.legal_moves()
        return random.choice(moves)


def mcts_agent(game_state):
    """Wrapper for agents.mcts_agent.MCTSAgent."""
    try:
        from agents.mcts_agent import MCTSAgent

        agent = MCTSAgent()
        return agent.select_move(game_state)
    except ImportError as e:
        print(f"[WARN] MCTSAgent import failed: {e}")
        return random_agent(game_state)


def mcts_prototype_agent(game_state):
    """Wrapper for agents.mcts_prototype_agent.MCTSAgent."""
    try:
        from agents.mcts_prototype_agent import MCTSAgent

        agent = MCTSAgent()
        return agent.select_move(game_state)
    except ImportError as e:
        print(f"[WARN] MCTSPrototypeAgent import failed: {e}")
        return random_agent(game_state)


def minimax_agent(game_state):
    """Wrapper for agents.minimax_agent.MinimaxAgent."""
    try:
        from agents.minimax_agent import MinimaxAgent

        agent = MinimaxAgent()
        return agent.select_move(game_state)
    except ImportError as e:
        print(f"[WARN] MinimaxAgent import failed: {e}")
        return random_agent(game_state)


AGENTS = {
    "random": random_agent,
    "mcts": mcts_agent,
    "mcts_prototype": mcts_prototype_agent,
    "minimax": minimax_agent,
    "minimax_agent": minimax_agent,
}


def print_board(game_state):
    """Print board to terminal."""
    board = game_state.board
    print("  ", end="")
    for c in range(1, board.num_cols + 1):
        print(f"{c:2}", end="")
    print()

    for r in range(1, board.num_rows + 1):
        print(f"{r:2}", end="")
        for c in range(1, board.num_cols + 1):
            stone = board.get(Point(r, c))
            if stone == Player.black:
                print(" X", end="")
            elif stone == Player.white:
                print(" O", end="")
            else:
                print(" .", end="")
        print()


def play_game(agent1_fn, agent2_fn, board_size=9, verbose=True):
    """Play one game and return (winner, move_count, duration_seconds)."""
    game = GameState.new_game(board_size)
    agents = {
        Player.black: agent1_fn,
        Player.white: agent2_fn,
    }

    move_count = 0
    start_time = time.time()

    while not game.is_over():
        if verbose:
            print(f"\n=== Move {move_count + 1}, {game.next_player.name} ===")
            print_board(game)

        agent_fn = agents[game.next_player]
        move = agent_fn(game)

        if verbose:
            print(f"Played: {move}")

        game = game.apply_move(move)
        move_count += 1

        if move_count > board_size * board_size * 2:
            print("[WARN] Too many moves; stopping this game early.")
            break

    duration = time.time() - start_time
    if game.is_over():
        winner = game.winner()
    else:
        winner = compute_game_result(game).winner

    if verbose:
        print("\n=== Final Board ===")
        print_board(game)
        if winner:
            print(f"Winner: {winner.name}")
        else:
            print("Draw")

    return winner, move_count, duration


def main():
    parser = argparse.ArgumentParser(description="Run Go AI matches")
    parser.add_argument(
        "--agent1",
        choices=AGENTS.keys(),
        default="random",
        help="Black agent",
    )
    parser.add_argument(
        "--agent2",
        choices=AGENTS.keys(),
        default="random",
        help="White agent",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=5,
        help="Board size (default: 5)",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=1,
        help="Number of games (default: 1)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only summary",
    )

    args = parser.parse_args()

    agent1 = AGENTS[args.agent1]
    agent2 = AGENTS[args.agent2]

    results = {Player.black: 0, Player.white: 0, None: 0}
    total_moves = 0
    total_time = 0

    for i in range(args.games):
        if not args.quiet:
            print(f"\n========== Game {i + 1}/{args.games} ==========")

        winner, moves, duration = play_game(
            agent1, agent2, args.size, verbose=not args.quiet
        )

        results[winner] += 1
        total_moves += moves
        total_time += duration

    print("\n========== Summary ==========")
    print(f"Games: {args.games}")
    print(f"Black ({args.agent1}) wins: {results[Player.black]}")
    print(f"White ({args.agent2}) wins: {results[Player.white]}")
    print(f"Draws: {results[None]}")
    print(f"Avg moves: {total_moves / args.games:.1f}")
    print(f"Avg time: {total_time / args.games:.2f}s")


if __name__ == "__main__":
    main()

