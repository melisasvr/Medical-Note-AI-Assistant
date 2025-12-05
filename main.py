"""
Medical Note AI Assistant
Helps physicians generate structured clinical notes from conversational input.
Includes voice input capability for hands-free dictation.
Supports multiple languages and persistent storage.
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import speech_recognition as sr
from pathlib import Path


class ClinicalNote:
    """Represents a structured clinical note following SOAP format."""
    
    def __init__(self, patient_id: str, physician_name: str, language: str = "en-US"):
        self.note_id = None  # Will be set when saved to database
        self.patient_id = patient_id
        self.physician_name = physician_name
        self.language = language
        self.timestamp = datetime.now()
        self.subjective = []
        self.objective = []
        self.assessment = []
        self.plan = []
        self.audio_data = None  # Store original audio recording
    
    def add_subjective(self, text: str):
        """Add chief complaint, HPI, ROS, etc."""
        self.subjective.append(text)
    
    def add_objective(self, text: str):
        """Add vitals, physical exam findings, lab results."""
        self.objective.append(text)
    
    def add_assessment(self, text: str):
        """Add diagnosis, differential, clinical impression."""
        self.assessment.append(text)
    
    def add_plan(self, text: str):
        """Add treatment plan, medications, follow-up."""
        self.plan.append(text)
    
    def set_audio_data(self, audio_bytes: bytes):
        """Store the original audio recording."""
        self.audio_data = audio_bytes
    
    def generate_note(self) -> str:
        """Generate formatted clinical note."""
        # Get language name for display
        lang_display = {
            'en-US': 'English',
            'es-ES': 'Spanish',
            'fr-FR': 'French',
            'it-IT': 'Italian',
            'tr-TR': 'Turkish',
            'de-DE': 'German'
        }.get(self.language, self.language)
        
        note = f"""
CLINICAL NOTE
Date: {self.timestamp.strftime('%Y-%m-%d %H:%M')}
Patient ID: {self.patient_id}
Physician: {self.physician_name}
Language: {lang_display}
{f"Note ID: {self.note_id}" if self.note_id else ""}

{'='*60}

SUBJECTIVE:
{self._format_section(self.subjective)}

OBJECTIVE:
{self._format_section(self.objective)}

ASSESSMENT:
{self._format_section(self.assessment)}

PLAN:
{self._format_section(self.plan)}

{'='*60}
Electronically signed by: {self.physician_name}
"""
        return note.strip()
    
    def _format_section(self, items: List[str]) -> str:
        """Format a section of the note."""
        if not items:
            return "  [Not documented]"
        return "\n".join(f"  - {item}" for item in items)
    
    def to_dict(self) -> Dict:
        """Export note as dictionary."""
        return {
            'note_id': self.note_id,
            'patient_id': self.patient_id,
            'physician': self.physician_name,
            'language': self.language,
            'timestamp': self.timestamp.isoformat(),
            'subjective': self.subjective,
            'objective': self.objective,
            'assessment': self.assessment,
            'plan': self.plan,
            'has_audio': self.audio_data is not None
        }


class NoteDatabase:
    """SQLite database for storing clinical notes and audio recordings."""
    
    def __init__(self, db_path: str = "clinical_notes.db"):
        """
        Initialize database connection and create tables if needed.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        self._create_tables()
        print(f"Database connected: {db_path}")
    
    def _create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Clinical notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinical_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                physician_name TEXT NOT NULL,
                language TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                subjective TEXT,
                objective TEXT,
                assessment TEXT,
                plan TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Audio recordings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_recordings (
                audio_id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                audio_data BLOB NOT NULL,
                audio_format TEXT DEFAULT 'wav',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (note_id) REFERENCES clinical_notes (note_id)
            )
        """)
        
        # Create indexes for faster searches
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_patient_id 
            ON clinical_notes (patient_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_physician 
            ON clinical_notes (physician_name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON clinical_notes (timestamp)
        """)
        
        self.conn.commit()
    
    def save_note(self, note: ClinicalNote) -> int:
        """
        Save a clinical note to the database.
        
        Args:
            note: ClinicalNote object to save
        
        Returns:
            The note_id of the saved note
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO clinical_notes 
            (patient_id, physician_name, language, timestamp, subjective, objective, assessment, plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            note.patient_id,
            note.physician_name,
            note.language,
            note.timestamp.isoformat(),
            json.dumps(note.subjective),
            json.dumps(note.objective),
            json.dumps(note.assessment),
            json.dumps(note.plan)
        ))
        
        note_id = cursor.lastrowid
        note.note_id = note_id
        
        # Save audio if present
        if note.audio_data:
            cursor.execute("""
                INSERT INTO audio_recordings (note_id, audio_data)
                VALUES (?, ?)
            """, (note_id, note.audio_data))
        
        self.conn.commit()
        print(f"Note saved with ID: {note_id}")
        return note_id
    
    def get_note(self, note_id: int) -> Optional[ClinicalNote]:
        """
        Retrieve a clinical note by ID.
        
        Args:
            note_id: ID of the note to retrieve
        
        Returns:
            ClinicalNote object or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clinical_notes WHERE note_id = ?", (note_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        note = ClinicalNote(row['patient_id'], row['physician_name'], row['language'])
        note.note_id = row['note_id']
        note.timestamp = datetime.fromisoformat(row['timestamp'])
        note.subjective = json.loads(row['subjective'])
        note.objective = json.loads(row['objective'])
        note.assessment = json.loads(row['assessment'])
        note.plan = json.loads(row['plan'])
        
        # Load audio if exists
        cursor.execute("SELECT audio_data FROM audio_recordings WHERE note_id = ?", (note_id,))
        audio_row = cursor.fetchone()
        if audio_row:
            note.audio_data = audio_row['audio_data']
        
        return note
    
    def search_notes(self, patient_id: Optional[str] = None, 
                     physician_name: Optional[str] = None,
                     start_date: Optional[datetime] = None,
                     end_date: Optional[datetime] = None,
                     limit: int = 100) -> List[ClinicalNote]:
        """
        Search for clinical notes with optional filters.
        
        Args:
            patient_id: Filter by patient ID
            physician_name: Filter by physician name
            start_date: Filter notes after this date
            end_date: Filter notes before this date
            limit: Maximum number of results
        
        Returns:
            List of ClinicalNote objects
        """
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM clinical_notes WHERE 1=1"
        params = []
        
        if patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)
        
        if physician_name:
            query += " AND physician_name = ?"
            params.append(physician_name)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        notes = []
        for row in rows:
            note = ClinicalNote(row['patient_id'], row['physician_name'], row['language'])
            note.note_id = row['note_id']
            note.timestamp = datetime.fromisoformat(row['timestamp'])
            note.subjective = json.loads(row['subjective'])
            note.objective = json.loads(row['objective'])
            note.assessment = json.loads(row['assessment'])
            note.plan = json.loads(row['plan'])
            notes.append(note)
        
        return notes
    
    def get_audio(self, note_id: int) -> Optional[bytes]:
        """
        Retrieve audio recording for a note.
        
        Args:
            note_id: ID of the note
        
        Returns:
            Audio data as bytes or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT audio_data FROM audio_recordings WHERE note_id = ?", (note_id,))
        row = cursor.fetchone()
        return row['audio_data'] if row else None
    
    def delete_note(self, note_id: int) -> bool:
        """
        Delete a clinical note and its associated audio.
        
        Args:
            note_id: ID of the note to delete
        
        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.cursor()
        
        # Check if note exists
        cursor.execute("SELECT note_id FROM clinical_notes WHERE note_id = ?", (note_id,))
        if not cursor.fetchone():
            return False
        
        # Delete audio first (foreign key)
        cursor.execute("DELETE FROM audio_recordings WHERE note_id = ?", (note_id,))
        
        # Delete note
        cursor.execute("DELETE FROM clinical_notes WHERE note_id = ?", (note_id,))
        
        self.conn.commit()
        print(f"Note {note_id} deleted")
        return True
    
    def get_statistics(self) -> Dict:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM clinical_notes")
        total_notes = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(DISTINCT patient_id) as total FROM clinical_notes")
        total_patients = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(DISTINCT physician_name) as total FROM clinical_notes")
        total_physicians = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM audio_recordings")
        total_audio = cursor.fetchone()['total']
        
        return {
            'total_notes': total_notes,
            'total_patients': total_patients,
            'total_physicians': total_physicians,
            'total_audio_recordings': total_audio
        }
    
    def close(self):
        """Close database connection."""
        self.conn.close()
        print("Database connection closed")


class VoiceRecorder:
    """Handles voice recording and transcription for clinical notes."""
    
    # Supported languages with their Google Speech Recognition codes
    SUPPORTED_LANGUAGES = {
        'en-US': 'English (US)',
        'es-ES': 'Spanish (Spain)',
        'fr-FR': 'French (France)',
        'it-IT': 'Italian (Italy)',
        'tr-TR': 'Turkish (Turkey)',
        'de-DE': 'German (Germany)'
    }
    
    def __init__(self, language: str = "en-US"):
        """
        Initialize voice recorder with specified language.
        
        Args:
            language: Language code (e.g., 'en-US', 'es-ES', 'fr-FR', etc.)
        """
        if language not in self.SUPPORTED_LANGUAGES:
            print(f"Warning: Language {language} not in supported list. Defaulting to en-US")
            language = "en-US"
        
        self.language = language
        self.recognizer = sr.Recognizer()
        # Adjust for ambient noise sensitivity
        self.recognizer.energy_threshold = 4000
        self.recognizer.dynamic_energy_threshold = True
        
        print(f"Voice recorder initialized for: {self.SUPPORTED_LANGUAGES[language]}")
    
    @classmethod
    def list_supported_languages(cls):
        """Display all supported languages."""
        print("\nSupported Languages:")
        print("-" * 40)
        for code, name in cls.SUPPORTED_LANGUAGES.items():
            print(f"  {code}: {name}")
        print("-" * 40)
    
    def record_from_microphone(self, duration: Optional[int] = None) -> tuple:
        """
        Record audio from microphone and transcribe to text.
        
        Args:
            duration: Optional recording duration in seconds. 
                     If None, records until silence is detected.
        
        Returns:
            Tuple of (transcribed text, raw audio bytes)
        """
        try:
            with sr.Microphone() as source:
                print("Adjusting for ambient noise... Please wait.")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                print(f"Recording in {self.SUPPORTED_LANGUAGES[self.language]}... Speak now!")
                if duration:
                    print(f"   (Will record for {duration} seconds)")
                    audio = self.recognizer.listen(source, timeout=duration, phrase_time_limit=duration)
                else:
                    print("   (Will stop after detecting silence)")
                    audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=60)
                
                print("Recording complete. Transcribing...")
                
                # Get raw audio bytes
                audio_bytes = audio.get_wav_data()
                
                # Use Google Speech Recognition with specified language
                text = self.recognizer.recognize_google(audio, language=self.language)
                print("Transcription successful!")
                return text, audio_bytes
                
        except sr.WaitTimeoutError:
            print("ERROR: No speech detected. Please try again.")
            return "", b""
        except sr.UnknownValueError:
            print("ERROR: Could not understand audio. Please speak more clearly.")
            return "", b""
        except sr.RequestError as e:
            print(f"ERROR: Could not request results from speech recognition service: {e}")
            return "", b""
        except Exception as e:
            print(f"ERROR: Error during recording: {e}")
            return "", b""
    
    def transcribe_audio_file(self, file_path: str) -> tuple:
        """
        Transcribe an existing audio file to text.
        Supports WAV, AIFF, and FLAC formats.
        
        Args:
            file_path: Path to audio file
        
        Returns:
            Tuple of (transcribed text, raw audio bytes)
        """
        try:
            with sr.AudioFile(file_path) as source:
                print(f"Loading audio file: {file_path}")
                audio = self.recognizer.record(source)
                
                # Get raw audio bytes
                audio_bytes = audio.get_wav_data()
                
                print(f"Transcribing in {self.SUPPORTED_LANGUAGES[self.language]}...")
                text = self.recognizer.recognize_google(audio, language=self.language)
                print("Transcription successful!")
                return text, audio_bytes
                
        except FileNotFoundError:
            print(f"ERROR: File not found: {file_path}")
            return "", b""
        except sr.UnknownValueError:
            print("ERROR: Could not understand audio. Audio quality may be poor.")
            return "", b""
        except sr.RequestError as e:
            print(f"ERROR: Error with speech recognition service: {e}")
            return "", b""
        except Exception as e:
            print(f"ERROR: Error transcribing file: {e}")
            return "", b""
    
    def record_with_pause_detection(self) -> tuple:
        """
        Record with intelligent pause detection.
        Stops recording after 2 seconds of silence.
        
        Returns:
            Tuple of (transcribed text, raw audio bytes)
        """
        try:
            with sr.Microphone() as source:
                print("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                print(f"Recording in {self.SUPPORTED_LANGUAGES[self.language]}...")
                print("   (Will auto-stop after 2 seconds of silence)")
                # Record until 2 seconds of silence
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=120)
                
                print("Silence detected. Processing...")
                
                # Get raw audio bytes
                audio_bytes = audio.get_wav_data()
                
                text = self.recognizer.recognize_google(audio, language=self.language)
                print("Transcription complete!")
                return text, audio_bytes
                
        except Exception as e:
            print(f"ERROR: {e}")
            return "", b""


class NoteParser:
    """Parses conversational input and extracts clinical information."""
    
    # Keywords for categorizing clinical information
    SUBJECTIVE_KEYWORDS = [
        'complains', 'reports', 'states', 'feels', 'experiencing',
        'symptoms', 'pain', 'discomfort', 'history', 'denies'
    ]
    
    OBJECTIVE_KEYWORDS = [
        'bp', 'blood pressure', 'heart rate', 'hr', 'temp', 'temperature',
        'exam', 'examination', 'auscultation', 'palpation', 'inspection',
        'lab', 'test', 'result', 'x-ray', 'imaging', 'vitals'
    ]
    
    ASSESSMENT_KEYWORDS = [
        'diagnosis', 'differential', 'impression', 'consistent with',
        'likely', 'suspect', 'presents with', 'appears to be'
    ]
    
    PLAN_KEYWORDS = [
        'prescribe', 'medication', 'treat', 'follow up', 'return',
        'refer', 'order', 'recommend', 'advise', 'therapy'
    ]
    
    @staticmethod
    def categorize_statement(statement: str) -> str:
        """Determine which SOAP section a statement belongs to."""
        statement_lower = statement.lower()
        
        # Check keywords in order of specificity
        for keyword in NoteParser.PLAN_KEYWORDS:
            if keyword in statement_lower:
                return 'plan'
        
        for keyword in NoteParser.ASSESSMENT_KEYWORDS:
            if keyword in statement_lower:
                return 'assessment'
        
        for keyword in NoteParser.OBJECTIVE_KEYWORDS:
            if keyword in statement_lower:
                return 'objective'
        
        for keyword in NoteParser.SUBJECTIVE_KEYWORDS:
            if keyword in statement_lower:
                return 'subjective'
        
        # Default to subjective for patient-reported information
        return 'subjective'
    
    @staticmethod
    def parse_encounter(text: str) -> Dict[str, List[str]]:
        """Parse encounter text into SOAP components."""
        # Split into sentences
        sentences = [s.strip() for s in text.replace('\n', '. ').split('.') if s.strip()]
        
        result = {
            'subjective': [],
            'objective': [],
            'assessment': [],
            'plan': []
        }
        
        for sentence in sentences:
            category = NoteParser.categorize_statement(sentence)
            result[category].append(sentence)
        
        return result


def create_note_from_text(encounter_text: str, patient_id: str, 
                          physician_name: str, language: str = "en-US") -> ClinicalNote:
    """
    Create a clinical note from conversational encounter text.
    
    Args:
        encounter_text: Free-text description of patient encounter
        patient_id: Patient identifier
        physician_name: Physician's name
        language: Language code for the note
    
    Returns:
        ClinicalNote object with structured information
    """
    note = ClinicalNote(patient_id, physician_name, language)
    parsed = NoteParser.parse_encounter(encounter_text)
    
    for item in parsed['subjective']:
        note.add_subjective(item)
    
    for item in parsed['objective']:
        note.add_objective(item)
    
    for item in parsed['assessment']:
        note.add_assessment(item)
    
    for item in parsed['plan']:
        note.add_plan(item)
    
    return note


def create_note_from_voice(patient_id: str, physician_name: str, 
                           language: str = "en-US",
                           audio_file: Optional[str] = None) -> ClinicalNote:
    """
    Create a clinical note from voice input.
    
    Args:
        patient_id: Patient identifier
        physician_name: Physician's name
        language: Language code (e.g., 'en-US', 'es-ES', 'fr-FR')
        audio_file: Optional path to audio file. If None, records from microphone.
    
    Returns:
        ClinicalNote object with structured information
    """
    recorder = VoiceRecorder(language)
    
    # Get transcription from voice
    if audio_file:
        encounter_text, audio_bytes = recorder.transcribe_audio_file(audio_file)
    else:
        encounter_text, audio_bytes = recorder.record_with_pause_detection()
    
    if not encounter_text:
        print("WARNING: No text transcribed. Creating empty note.")
        return ClinicalNote(patient_id, physician_name, language)
    
    print(f"\nTranscribed text:\n{encounter_text}\n")
    
    # Parse and create note
    note = create_note_from_text(encounter_text, patient_id, physician_name, language)
    
    # Attach audio data
    if audio_bytes:
        note.set_audio_data(audio_bytes)
    
    return note


# Example usage and demonstration
if __name__ == "__main__":
    print("="*60)
    print("MEDICAL NOTE AI ASSISTANT")
    print("Multi-Language Voice Input with Database Storage")
    print("="*60)
    
    # Initialize database
    db = NoteDatabase("clinical_notes.db")
    
    # Show supported languages
    VoiceRecorder.list_supported_languages()
    
    # Example 1: Create and save English note
    print("\nEXAMPLE 1: English Note with Database Storage")
    print("-"*60)
    
    encounter = """
    Patient complains of persistent cough for 2 weeks with yellow sputum.
    Reports mild fever and fatigue. Denies shortness of breath or chest pain.
    Vitals: BP 128/82, HR 88, Temp 99.2F, O2 sat 98% on room air.
    Lung exam reveals coarse crackles in right lower lobe.
    Cardiac exam normal. No wheezing noted.
    Diagnosis: Community-acquired pneumonia, right lower lobe.
    Will prescribe Azithromycin 500mg daily for 5 days.
    Recommend increased fluid intake and rest.
    Follow up in 1 week or sooner if symptoms worsen.
    """
    
    note = create_note_from_text(
        encounter_text=encounter,
        patient_id="PT-12345",
        physician_name="Dr. Sarah Johnson",
        language="en-US"
    )
    
    # Save to database
    note_id = db.save_note(note)
    print(note.generate_note())
    
    # Example 2: Search and retrieve
    print("\n\nEXAMPLE 2: Search and Retrieve Notes")
    print("-"*60)
    
    # Search by patient
    found_notes = db.search_notes(patient_id="PT-12345")
    print(f"Found {len(found_notes)} note(s) for patient PT-12345")
    
    # Retrieve specific note
    retrieved_note = db.get_note(note_id)
    if retrieved_note:
        print(f"\nRetrieved note #{note_id}")
        print(f"   Patient: {retrieved_note.patient_id}")
        print(f"   Physician: {retrieved_note.physician_name}")
        print(f"   Language: {retrieved_note.language}")
        print(f"   Date: {retrieved_note.timestamp.strftime('%Y-%m-%d %H:%M')}")
    
    # Example 3: Database statistics
    print("\n\nEXAMPLE 3: Database Statistics")
    print("-"*60)
    stats = db.get_statistics()
    for key, value in stats.items():
        print(f"   {key.replace('_', ' ').title()}: {value}")
    
    # Example 4: Multi-language voice examples
    print("\n\nEXAMPLE 4: Multi-Language Voice Input")
    print("-"*60)
    print("\nTo test REAL voice recording, uncomment one of these:\n")
    
    print("# English voice recording:")
    print("# note_voice = create_note_from_voice(")
    print("#     patient_id='PT-99999',")
    print("#     physician_name='Dr. Test',")
    print("#     language='en-US'")
    print("# )")
    print("# db.save_note(note_voice)")
    print("# print(note_voice.generate_note())")
    
    print("\n# Spanish voice recording:")
    print("# note_es = create_note_from_voice(")
    print("#     patient_id='PT-67890',")
    print("#     physician_name='Dr. Maria Garcia',")
    print("#     language='es-ES'")
    print("# )")
    print("# db.save_note(note_es)")
    
    # Close database
    print("\n" + "="*60)
    print("SETUP INSTRUCTIONS:")
    print("="*60)
    print("\n1. Install required packages:")
    print("   pip install SpeechRecognition pyaudio")
    print("\n2. Database file created automatically: clinical_notes.db")
    print("\n3. For audio file support:")
    print("   pip install pydub")
    print("\n4. Platform-specific:")
    print("   Windows: pip install pyaudio")
    print("   macOS: brew install portaudio && pip install pyaudio")
    print("   Linux: sudo apt-get install python3-pyaudio")
    print("\n5. Supported languages:")
    print("   English, Spanish, French, Italian, Turkish, German")
    print("\n6. To test voice recording:")
    print("   Uncomment the voice recording examples above")
    print("\n" + "="*60)
    
    # Clean up
    db.close()