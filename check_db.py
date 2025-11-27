from database import SessionLocal, Game

def check_games():
    db = SessionLocal()
    try:
        games = db.query(Game).all()
        print(f"Total games in DB: {len(games)}")
        for game in games:
            print(f"ID: {game.id}, Title: {game.title}, Views: {game.views}, Rating: {game.rating}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_games()
