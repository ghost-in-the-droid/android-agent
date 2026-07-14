# LangChain Integration — commands from this demo
# https://ghostinthedroid.com/features/integrations/

for i in 1 2 3 4 5; do python scripts/showcase/langchain_script.py; done
sqlite3 -header -column scripts/showcase/posts.db "SELECT subreddit, upvotes, comments, substr(title,1,38) title FROM posts"
