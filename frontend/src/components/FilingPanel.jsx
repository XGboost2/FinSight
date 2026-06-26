import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import {
  FileText, MessageCircle, Loader, ChevronRight, Upload, CheckCircle,
  AlertCircle, ImagePlus, Mic, Square, Volume2, VolumeX,
} from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL ?? ''

const SAMPLE_QUESTIONS = [
  'What are the main risk factors?',
  'Summarise the revenue and earnings trend.',
  'What does management say about future outlook?',
  'What happened in the most recent quarter?',
  'Are there any recent material events or announcements?',
]

const MODELS = [
  { value: 'auto',               label: 'Auto',             group: 'Kimi' },
  { value: 'kimi-k2.6',          label: 'Kimi K2.6',        group: 'Kimi' },
  { value: 'deepseek-v4-flash',  label: 'DS Flash',         group: 'DeepSeek' },
  { value: 'deepseek-v4-pro',   label: 'DS Pro',           group: 'DeepSeek' },
  { value: 'claude-haiku-4-5',   label: 'Haiku',            group: 'Anthropic' },
  { value: 'claude-sonnet-4-6',  label: 'Sonnet',           group: 'Anthropic' },
  { value: 'claude-opus-4-7',    label: 'Opus',             group: 'Anthropic' },
  { value: 'gpt-4o-mini',        label: 'GPT-4o Mini',      group: 'OpenAI' },
  { value: 'gpt-4o',             label: 'GPT-4o',           group: 'OpenAI' },
]

const LLM_MODES = [
  { value: 'cloud', label: 'Cloud', hint: 'Hosted models' },
  { value: 'local', label: 'Local', hint: 'Runs on your Mac' },
]

const LOCAL_MODELS = [
  { value: 'qwen3.5:0.8b', label: 'Qwen3.5 0.8B (recommended)' },
  { value: 'microsoft/Phi-3.5-mini-instruct', label: 'Phi-3.5 Mini' },
  { value: 'google/gemma-2-2b-it', label: 'Gemma 2 2B' },
  { value: 'meta-llama/Llama-3.2-3B-Instruct', label: 'Llama 3.2 3B' },
]

export default function FilingPanel({ ticker, companyName, filingId, filing, fetchingFiling, sessionId }) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState([])
  const [chatLoading, setChatLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState('auto')
  const [llmMode, setLlmMode] = useState(() => localStorage.getItem('finsight-llm-mode') || 'cloud')
  const [selectedLocalModel, setSelectedLocalModel] = useState(
    () => localStorage.getItem('finsight-local-model') || 'qwen3.5:0.8b',
  )
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadType, setUploadType] = useState('10-K')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadedFiling, setUploadedFiling] = useState(null)
  const [mediaBusy, setMediaBusy] = useState('')
  const [mediaError, setMediaError] = useState('')
  const [recording, setRecording] = useState(false)
  const [voiceResponses, setVoiceResponses] = useState(false)
  const [speakingIndex, setSpeakingIndex] = useState(null)
  const bottomRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const audioRef = useRef(null)
  const audioUrlRef = useRef(null)

  const activeFiling = uploadedFiling ?? filing
  const activeFilingId = uploadedFiling?.filing_id ?? filingId

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, chatLoading])

  useEffect(() => {
    setHistory([])
    setQuestion('')
    audioRef.current?.pause()
    if (audioRef.current) audioRef.current.currentTime = 0
    setSpeakingIndex(null)
  }, [activeFilingId])

  useEffect(() => {
    setUploadedFiling(null)
    setUploadFile(null)
    setUploadError('')
    setUploadType('10-K')
  }, [ticker])

  useEffect(() => {
    localStorage.setItem('finsight-llm-mode', llmMode)
  }, [llmMode])

  useEffect(() => {
    localStorage.setItem('finsight-local-model', selectedLocalModel)
  }, [selectedLocalModel])

  useEffect(() => () => {
    audioRef.current?.pause()
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    mediaRecorderRef.current?.stream?.getTracks().forEach(track => track.stop())
  }, [])

  const speakAnswer = async (text, index) => {
    if (!text || speakingIndex !== null) return
    setMediaError('')
    setSpeakingIndex(index)
    try {
      audioRef.current?.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      const { data } = await axios.post(
        `${API_URL}/api/multimodal/speech`,
        { text },
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(data)
      audioUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => setSpeakingIndex(null)
      audio.onerror = () => {
        setSpeakingIndex(null)
        setMediaError('Audio playback failed.')
      }
      await audio.play()
    } catch (e) {
      setSpeakingIndex(null)
      setMediaError(e.response?.data?.detail || 'Local speech synthesis failed.')
    }
  }

  const stopSpeaking = () => {
    audioRef.current?.pause()
    if (audioRef.current) audioRef.current.currentTime = 0
    setSpeakingIndex(null)
  }

  const send = async (q) => {
    const text = q.trim()
    if (!text || !activeFilingId || chatLoading) return
    setQuestion('')
    setHistory(h => [...h, { role: 'user', text }])
    setChatLoading(true)

    try {
      const headers = sessionId ? { 'X-Session-ID': sessionId } : {}
      const { data } = await axios.post(`${API_URL}/api/chat`, {
        question: text,
        ticker: ticker,
        filing_id: activeFilingId,
        model: llmMode === 'local'
          ? selectedLocalModel
          : selectedModel === 'auto'
            ? null
            : selectedModel,
        llm_mode: llmMode,
        session_id: sessionId ?? undefined,
      }, { headers })
      const cacheBadge = data.from_cache ? ' · cached' : ''
      const historyBadge = data.history_len > 0 ? ` · ${data.history_len} turns` : ''
      const answerId = `answer-${Date.now()}-${Math.random()}`
      setHistory(h => [...h, {
        id: answerId,
        role: 'assistant',
        text: data.answer,
        meta: `${data.llm_mode === 'local' ? 'Local' : 'Cloud'} · ${data.model_used} · $${data.cost_usd.toFixed(4)} · ${Math.round(data.latency_ms)}ms${cacheBadge}${historyBadge}`,
      }])
      if (voiceResponses) void speakAnswer(data.answer, answerId)
    } catch (e) {
      setHistory(h => [...h, {
        role: 'error',
        text: e.response?.data?.detail || 'Request failed — check backend logs.',
      }])
    } finally {
      setChatLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    send(question)
  }

  const handleUpload = async (e) => {
    e.preventDefault()
    if (!ticker || !uploadFile || uploading) return

    const form = new FormData()
    form.append('file', uploadFile)
    form.append('ticker', ticker)
    form.append('filing_type', uploadType)
    form.append('company_name', companyName || '')

    setUploading(true)
    setUploadError('')
    try {
      const { data } = await axios.post(`${API_URL}/api/documents/ingest`, form)
      setUploadedFiling({
        filing_id: data.filing_id,
        company_name: data.company_name || companyName,
        ticker: data.ticker,
        filing_type: data.filing_type,
        filed_date: data.filed_date || '—',
        chunk_count: data.chunk_count,
        filename: data.filename,
      })
      setHistory([])
      setQuestion('')
      setUploadFile(null)
    } catch (e) {
      setUploadError(e.response?.data?.detail || 'Upload failed — check backend logs.')
    } finally {
      setUploading(false)
    }
  }

  const handleQuestionImage = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || mediaBusy) return
    const form = new FormData()
    form.append('file', file)
    setMediaBusy('Reading handwriting…')
    setMediaError('')
    try {
      const { data } = await axios.post(`${API_URL}/api/multimodal/ocr`, form)
      setQuestion(data.text)
    } catch (error) {
      setMediaError(error.response?.data?.detail || 'Handwriting recognition failed.')
    } finally {
      setMediaBusy('')
    }
  }

  const transcribeRecording = async (blob) => {
    const form = new FormData()
    form.append('file', blob, 'question.webm')
    setMediaBusy('Transcribing speech…')
    setMediaError('')
    try {
      const { data } = await axios.post(`${API_URL}/api/multimodal/transcribe`, form)
      setQuestion(data.text)
    } catch (error) {
      setMediaError(error.response?.data?.detail || 'Speech transcription failed.')
    } finally {
      setMediaBusy('')
    }
  }

  const toggleRecording = async () => {
    if (recording) {
      mediaRecorderRef.current?.stop()
      setRecording(false)
      return
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setMediaError('Audio recording is not supported by this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const options = MediaRecorder.isTypeSupported?.('audio/webm')
        ? { mimeType: 'audio/webm' }
        : undefined
      const recorder = new MediaRecorder(stream, options)
      audioChunksRef.current = []
      recorder.ondataavailable = event => {
        if (event.data.size) audioChunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach(track => track.stop())
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        if (blob.size) void transcribeRecording(blob)
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setMediaError('')
      setRecording(true)
    } catch {
      setMediaError('Microphone permission was denied.')
    }
  }

  return (
    <div className="filing-panel glass-card">
      <div className="panel-header">
        <FileText size={18} />
        <h2>SEC Filings</h2>
      </div>

      {!ticker && (
        <p className="panel-empty">
          Search for a company to load its SEC filings (10-K, 10-Q, 8-K) and chat with them.
        </p>
      )}

      {fetchingFiling && (
        <div className="filing-loading">
          <Loader size={16} className="spin" />
          <span>Fetching SEC EDGAR filings for <strong>{ticker}</strong>…</span>
        </div>
      )}

      {ticker && !fetchingFiling && (
        <form className="document-upload" onSubmit={handleUpload}>
          <div className="upload-heading">
            <Upload size={14} />
            <span>Upload document</span>
          </div>
          <label className="upload-file">
            <input
              type="file"
              onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
              disabled={uploading}
            />
            <Upload size={13} />
            <span>{uploadFile ? uploadFile.name : 'Choose file: PDF, Word, PowerPoint, Excel, image, audio, HTML, CSV, JSON, XML, ZIP, EPub'}</span>
          </label>
          <p className="upload-description">
            MarkItDown converts many formats to Markdown, infers the uploaded company from the document, then indexes it with Neo4j vectorless graph RAG.
          </p>
          <div className="upload-controls">
            <select
              value={uploadType}
              onChange={e => setUploadType(e.target.value)}
              disabled={uploading}
              className="upload-select"
              aria-label="Filing type"
            >
              <option value="10-K">10-K</option>
              <option value="10-Q">10-Q</option>
              <option value="8-K">8-K</option>
              <option value="CUSTOM-DOC">Custom</option>
            </select>
            <button type="submit" className="upload-submit" disabled={!uploadFile || uploading}>
              {uploading ? <Loader size={13} className="spin" /> : <Upload size={13} />}
              <span>{uploading ? 'Indexing' : uploadFile ? 'Upload' : 'Choose file first'}</span>
            </button>
          </div>
          {uploadedFiling && (
            <div className="upload-status upload-ok">
              <CheckCircle size={13} />
              <span>{uploadedFiling.company_name || uploadedFiling.ticker || 'Document'} indexed as {uploadedFiling.filing_type} with Neo4j graph RAG</span>
            </div>
          )}
          {uploadError && (
            <div className="upload-status upload-error">
              <AlertCircle size={13} />
              <span>{uploadError}</span>
            </div>
          )}
        </form>
      )}

      {activeFiling && !fetchingFiling && (
        <>
          <div className="filing-meta">
            {[
              ['Company', activeFiling.company_name || companyName],
              ['Type', activeFiling.filing_type],
              ['Filed', activeFiling.filed_date || '—'],
              ['Indexed', `${activeFiling.chunk_count} chunks`],
              ...(activeFiling.filename ? [['Source', activeFiling.filename]] : []),
            ].map(([label, value]) => (
              <div key={label} className="meta-row">
                <span className="meta-label">{label}</span>
                <span className={`meta-value${label === 'Type' ? ' badge' : ''}`}>{value}</span>
              </div>
            ))}
          </div>

          <div className="divider" />

          <div className="chat-area">
            <div className="chat-label">
              <MessageCircle size={14} />
              <span>Ask the filings</span>
            </div>

            {history.length === 0 && (
              <div className="sample-questions">
                {SAMPLE_QUESTIONS.map(q => (
                  <button key={q} className="sample-q" onClick={() => send(q)}>
                    <ChevronRight size={12} />
                    {q}
                  </button>
                ))}
              </div>
            )}

            <div className="chat-history">
              {history.map((msg, i) => (
                <div key={i} className={`msg ${msg.role}`}>
                  <p className="msg-text">{msg.text}</p>
                  {msg.meta && <span className="msg-meta">{msg.meta}</span>}
                  {msg.role === 'assistant' && (
                    <button
                      type="button"
                      className="speak-message"
                      onClick={() => speakingIndex === msg.id ? stopSpeaking() : speakAnswer(msg.text, msg.id)}
                      aria-label={speakingIndex === msg.id ? 'Stop speaking' : 'Read answer aloud'}
                    >
                      {speakingIndex === msg.id
                        ? <><VolumeX size={12} /> Stop</>
                        : <><Volume2 size={12} /> Listen</>}
                    </button>
                  )}
                </div>
              ))}
              {chatLoading && (
                <div className="msg assistant loading">
                  <Loader size={12} className="spin" />
                  <span>Thinking…</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="llm-bar">
              <div className="llm-mode-switch" role="tablist" aria-label="LLM mode">
                {LLM_MODES.map(mode => (
                  <button
                    key={mode.value}
                    type="button"
                    role="tab"
                    aria-selected={llmMode === mode.value}
                    className={`llm-mode-pill${llmMode === mode.value ? ' llm-mode-pill-active' : ''}`}
                    onClick={() => setLlmMode(mode.value)}
                    title={mode.hint}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>

              {llmMode === 'local' ? (
                <label className="llm-model-field" htmlFor="local-model-select">
                  <span>Local model</span>
                  <select
                    id="local-model-select"
                    className="llm-model-select"
                    value={selectedLocalModel}
                    onChange={e => setSelectedLocalModel(e.target.value)}
                  >
                    {LOCAL_MODELS.map(model => (
                      <option key={model.value} value={model.value}>{model.label}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="llm-model-field" htmlFor="cloud-model-select">
                  <span>Cloud model</span>
                  <select
                    id="cloud-model-select"
                    className="llm-model-select"
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                  >
                    {MODELS.map(model => (
                      <option key={model.value} value={model.value}>
                        {model.label}{model.group ? ` · ${model.group}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            <div className="llm-hint">
              {llmMode === 'local'
                ? 'Local mode uses Ollama and the selected local model.'
                : 'Cloud mode uses Kimi first, then DeepSeek, with local as fallback.'}
            </div>

            <form onSubmit={handleSubmit} className="chat-form">
              <div className="chat-composer">
                <label className="chat-tool" title="Upload a handwritten question">
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={handleQuestionImage}
                    disabled={chatLoading || Boolean(mediaBusy)}
                    aria-label="Upload handwritten question"
                  />
                  <ImagePlus size={16} />
                </label>
                <button
                  type="button"
                  className={`chat-tool${recording ? ' chat-tool-recording' : ''}`}
                  onClick={toggleRecording}
                  disabled={chatLoading || Boolean(mediaBusy)}
                  aria-label={recording ? 'Stop recording' : 'Record voice question'}
                  title={recording ? 'Stop recording' : 'Record voice question'}
                >
                  {recording ? <Square size={14} /> : <Mic size={16} />}
                </button>
                <input
                  type="text"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  placeholder="Ask about filings — type, speak, or upload handwriting…"
                  disabled={chatLoading || Boolean(mediaBusy)}
                  className="chat-input"
                />
              </div>
              <button
                type="submit"
                disabled={!question.trim() || chatLoading || Boolean(mediaBusy)}
                className="chat-submit"
              >
                Ask
              </button>
              <div className="multimodal-options">
                <label className="voice-toggle">
                  <input
                    type="checkbox"
                    checked={voiceResponses}
                    onChange={e => setVoiceResponses(e.target.checked)}
                  />
                  <Volume2 size={12} />
                  Speak answers
                </label>
                {recording && <span className="media-state recording-state">Recording… click stop when finished</span>}
                {mediaBusy && <span className="media-state"><Loader size={11} className="spin" /> {mediaBusy}</span>}
                {mediaError && <span className="media-state media-error">{mediaError}</span>}
              </div>
            </form>
          </div>
        </>
      )}
    </div>
  )
}
