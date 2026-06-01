from pinecone import Pinecone
import PyPDF2

api_key=os.getenv("PINECONE_API_KEY")
index = pc.Index("eom-realestate")

def read_pdf(file_path):
    reader = PyPDF2.PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

def make_chunks(text, size=300):
    words = text.split()
    chunks = []
    for i in range(0, len(words), size):
        chunk = " ".join(words[i:i+size])
        chunks.append(chunk)
    return chunks

pdf_text = read_pdf("eom_realestate.pdf")
chunks = make_chunks(pdf_text)
records = [{"id": f"chunk-{i}", "text": c} for i, c in enumerate(chunks)]
index.upsert_records("default", records)
print(f"Done! {len(records)} chunks uploaded!")