"""Simple number guessing mini-game."""

import random


MAX_ATTEMPTS = 7


def prompt_range() -> tuple[int, int]:
    while True:
        raw = input("Enter a range (e.g., 1 100): ").strip()
        if not raw:
            print("Range cannot be empty. Try again.")
            continue
        parts = raw.split()
        if len(parts) != 2:
            print("Please enter two numbers like: 1 100")
            continue
        try:
            low, high = int(parts[0]), int(parts[1])
        except ValueError:
            print("Both values must be integers.")
            continue
        if low >= high:
            print("The first number must be smaller than the second.")
            continue
        return low, high


def play_round() -> None:
    low, high = prompt_range()
    secret = random.randint(low, high)
    attempts_left = MAX_ATTEMPTS

    print(
        f"I'm thinking of a number between {low} and {high}. "
        f"You have {MAX_ATTEMPTS} attempts."
    )

    while attempts_left > 0:
        guess_raw = input(
            f"Enter your guess ({attempts_left} left, or 'q' to quit): "
        ).strip()
        if guess_raw.lower() == "q":
            print("You exited the round.")
            return
        try:
            guess = int(guess_raw)
        except ValueError:
            print("Please enter a valid integer.")
            continue

        attempts_left -= 1

        if guess == secret:
            print("🎉 Correct! You found the number!")
            return
        if guess < secret:
            print("Too low!")
        else:
            print("Too high!")

    print(f"Out of attempts! The number was {secret}.")


def main() -> None:
    print("Welcome to the Number Guessing Game!")
    while True:
        play_round()
        again = input("Play again? (y/n): ").strip().lower()
        if again != "y":
            print("Thanks for playing!")
            break


if __name__ == "__main__":
    main()
