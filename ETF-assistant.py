import os
import json
from openai import OpenAI


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


def chat_with_assistant():
    print("You can start chatting with the assistant. Type 'exit' to end the conversation.")
    while True:
        user_input = input("$ ")
        if user_input.lower() == 'exit':
            break

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

        print(f"{bcolors.OKGREEN}{
              message_content.value}{bcolors.ENDC}")
        if citations:
            print("Citations:")
            print("\n".join(citations))


if __name__ == "__main__":
    chat_with_assistant()
