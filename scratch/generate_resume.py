from docx import Document

def generate_test_resume():
    doc = Document()
    doc.add_paragraph("John Doe\nSoftware Engineer\nSkills: Python, React, SQL, Git, FastAPI, Docker, AWS")
    doc.save("test_resume.docx")
    print("test_resume.docx generated successfully!")

if __name__ == "__main__":
    generate_test_resume()
