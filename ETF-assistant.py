import os
import json
from openai import OpenAI

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

# Create a thread and attach the files to the message
thread = client.beta.threads.create(
    messages=[
        {
            "role": "user",
            "content": "When can I reenroll in health insurance with sick leave?",
            # Attach the new files to the message.
            "attachments": [
                {"file_id": message_file.id, "tools": [{"type": "file_search"}]} for message_file in message_files
            ],
        }
    ]
)

# The thread now has a vector store with those files in its tool resources.
print(thread.tool_resources.file_search)

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

print("===================")
print(message_content.value)
print("=== Citations ===")
print("\n".join(citations))
print("=== Annotations ===")

# Retrieve the vector store
vector_store = client.beta.vector_stores.retrieve(
    vector_store_id=vector_store.id)

# List the files in the vector store
files = client.beta.vector_stores.files.list(vector_store_id=vector_store.id)

# Print the file details
print("Files in the vector store:")
for file in files:
    print(f"File ID: {file.id}")