from openai import OpenAI

with open('.zshrc', 'r') as f:
    api_key = f.read().strip()
    print("API key loaded successfully.")

client = OpenAI(api_key=api_key)

assistant = client.beta.assistants.create(
    name="Employee Trust Funds Customer Service Assistant",
    instructions="You are an expert ETF employee. Use you knowledge base to answer questions from customers.",
    model="gpt-4o-mini",
    tools=[{"type": "file_search"}],
)

vector_store = client.beta.vector_stores.create(name="ETF Documents")

# Ready the files for upload to OpenAI
file_paths = ["etf/et4118.pdf", "etf/et4121.pdf", "etf/et4132.pdf"]
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
    tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
)

# Upload the user provided file to OpenAI
message_file = client.files.create(
    file=open("etf/et4121.pdf", "rb"), purpose="assistants"
)

# Create a thread and attach the file to the message
thread = client.beta.threads.create(
    messages=[
        {
            "role": "user",
            "content": "What is the cost of buying service?",
            # Attach the new file to the message.
            "attachments": [
                {"file_id": message_file.id, "tools": [
                    {"type": "file_search"}]}
            ],
        }
    ]
)

# The thread now has a vector store with that file in its tool resources.
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

print(message_content.value)
print("\n".join(citations))
