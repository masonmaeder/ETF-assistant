import markdown
import os
import json
from openai import OpenAI
from flask import Flask, request, render_template_string, session

app = Flask(__name__)
app.config["SECRET_KEY"] = "your_secret_key"


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


with open('.zshrc', 'r') as f:
    api_key = f.read().strip()
    print("API key loaded successfully.")

client = OpenAI(api_key=api_key)

assistant = client.beta.assistants.create(
    name="Employee Trust Funds Customer Service Assistant",
    instructions="You are an expert ETF employee. Use your knowledge base to answer questions from customers.",
    model="gpt-4o-mini",
    tools=[{"type": "file_search"}],
)

vector_store = client.beta.vector_stores.create(name="ETF Documents")

# List all files in the etf/ directory
file_paths = [os.path.join("etf", file)
              for file in os.listdir("etf")]

# Initialize message_files
message_files = []

# Upload all files
file_streams = [open(path, "rb") for path in file_paths]

# Use the upload and poll SDK helper to upload the files, add them to the vector store,
# and poll the status of the file batch for completion.
file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
    vector_store_id=vector_store.id, files=file_streams
)

# You can print the status and the file counts of the batch to see the result of this operation.
print(file_batch.status)
print(file_batch.file_counts)

assistant = client.beta.assistants.update(
    assistant_id=assistant.id,
    tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
)

# Upload the user provided files to OpenAI
message_files = [client.files.create(
    file=open(path, "rb"), purpose="assistants") for path in file_paths]


@app.route("/", methods=["GET", "POST"])
def chat_with_assistant():
    # Clear the session at the beginning of each request
    session.clear()

    if "conversation" not in session:
        session["conversation"] = []

    if request.method == "POST":
        user_input = request.form["user_input"]
        session["conversation"].append({"role": "user", "content": user_input})

        # Create a thread and attach the files to the message
        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": user_input,
                    # Attach the new files to the message.
                    "attachments": [
                        {"file_id": message_file.id, "tools": [{"type": "file_search"}]} for message_file in message_files
                    ],
                }
            ]
        )

        # The thread now has a vector store with those files in its tool resources.
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id
        )

        messages = list(client.beta.threads.messages.list(
            thread_id=thread.id, run_id=run.id))

        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f"[{index}]")
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        html_content = markdown.markdown(message_content.value)
        citations_html = "<br>".join(citations)

        session["conversation"].append(
            {"role": "assistant", "content": html_content, "citations": citations_html})

    conversation_html = ""
    for message in session["conversation"]:
        if message["role"] == "user":
            conversation_html += f'<div class="user-message">{
                message["content"]}</div>'
        else:
            conversation_html += f'<div class="assistant-message">{
                message["content"]}</div>'
            if message["citations"]:
                conversation_html += f'<div class="citations">Learn more:<br>{
                    message["citations"]}</div>'

    return render_template_string("""
        <html>

        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }

                .user-message {
                    color: blue;
                    margin-bottom: 10px;
                    background-color: #e1f5fe;
                    padding: 10px;
                    border-radius: 10px;
                    max-width: 60%;
                    text-align: left;
                }

                .assistant-message {
                    color: green;
                    margin-bottom: 10px;
                    background-color: #e8f5e9;
                    padding: 10px;
                    border-radius: 10px;
                    max-width: 60%;
                    text-align: left;
                }

                .citations {
                    margin-left: 20px;
                    font-size: 0.9em;
                    color: gray;
                }

                form {
                    margin-top: 20px;
                }

                input[type="text"] {
                    width: 100%;
                    padding: 10px;
                    margin: 10px 0;
                    box-sizing: border-box;
                }

                input[type="submit"] {
                    background-color: #4CAF50;
                    color: white;
                    padding: 10px 20px;
                    border: none;
                    cursor: pointer;
                }

                input[type="submit"]:hover {
                    background-color: #45a049;
                }

                .logo {
                    text-align: center;
                }
            </style>
        </head>

        <body>
            <div class="logo">
                <img src="https://etfonline.wi.gov/images/detf_log.jpg" alt="Centered Image">
            </div>
            <div>
                {{ conversation_html|safe }}
            </div>
            <form method="post">
                <label for="user_input">How can I help you?</label><br>
                <input type="text" id="user_input" name="user_input"><br>
                <input type="submit" value="Submit">
            </form>
        </body>

        </html>
    """, conversation_html=conversation_html)


if __name__ == "__main__":
    app.run()
