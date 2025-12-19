import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, BookOpen, Upload, Youtube, Trash2, Plus, RefreshCw, 
  BarChart3, FileText, Video, File, AlertCircle, CheckCircle, 
  Loader2, Send, X, Bot, User 
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const API_URL = 'http://localhost:8000';

function App() {
  const [courses, setCourses] = useState([]);
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('query');
  const [notification, setNotification] = useState(null);

  // Chat / Query State
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]); 
  const [queryLoading, setQueryLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Course creation state
  const [newCourse, setNewCourse] = useState({ name: '', description: '', category: 'General' });
  
  // Material upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [youtubeTitle, setYoutubeTitle] = useState('');

  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchHealth();
    fetchCourses();
    fetchStats();
  }, []);

  // Auto-scroll to bottom when chat history updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, queryLoading]);

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 4000);
  };

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_URL}/`);
      const data = await res.json();
      setHealth(data);
    } catch (err) {
      console.error('Health check failed:', err);
    }
  };

  const fetchCourses = async () => {
    try {
      const res = await fetch(`${API_URL}/courses`);
      const data = await res.json();
      setCourses(data);
    } catch (err) {
      showNotification('Failed to fetch courses', 'error');
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_URL}/stats`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error('Stats fetch failed:', err);
    }
  };

  const createCourse = async (e) => {
    e.preventDefault();
    if (!newCourse.name.trim()) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/courses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newCourse)
      });

      if (res.ok) {
        showNotification('Course created successfully!');
        setNewCourse({ name: '', description: '', category: 'General' });
        fetchCourses();
        fetchStats();
      } else {
        const err = await res.json();
        showNotification(err.detail || 'Failed to create course', 'error');
      }
    } catch (err) {
      showNotification('Network error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const uploadMaterial = async (e) => {
    e.preventDefault();
    if (!selectedCourse || !uploadFile) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('title', uploadTitle);

    try {
      const res = await fetch(`${API_URL}/courses/${selectedCourse.id}/materials/upload`, {
        method: 'POST',
        body: formData
      });

      if (res.ok) {
        showNotification('Material uploaded successfully!');
        setUploadFile(null);
        setUploadTitle('');
        if (fileInputRef.current) fileInputRef.current.value = '';
        fetchCourses();
        fetchStats();
      } else {
        const err = await res.json();
        showNotification(err.detail || 'Upload failed', 'error');
      }
    } catch (err) {
      showNotification('Network error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const addYoutubeVideo = async (e) => {
    e.preventDefault();
    if (!selectedCourse || !youtubeUrl.trim()) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/courses/${selectedCourse.id}/materials/youtube`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: youtubeUrl, title: youtubeTitle })
      });

      if (res.ok) {
        showNotification('YouTube video added successfully!');
        setYoutubeUrl('');
        setYoutubeTitle('');
        fetchCourses();
        fetchStats();
      } else {
        const err = await res.json();
        showNotification(err.detail || 'Failed to add video', 'error');
      }
    } catch (err) {
      showNotification('Network error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const rebuildDatabase = async () => {
    if (!confirm('Rebuild the entire database? This may take a few minutes.')) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/rebuild`, { method: 'POST' });
      const data = await res.json();
      
      if (res.ok) {
        showNotification(`Database rebuilt: ${data.total_chunks} chunks indexed`);
        fetchHealth();
      } else {
        showNotification(data.detail || 'Rebuild failed', 'error');
      }
    } catch (err) {
      showNotification('Network error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const deleteCourse = async (courseId) => {
    if (!confirm('Delete this course and all its materials?')) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/courses/${courseId}`, { method: 'DELETE' });
      
      if (res.ok) {
        showNotification('Course deleted successfully');
        if (selectedCourse?.id === courseId) setSelectedCourse(null);
        fetchCourses();
        fetchStats();
      } else {
        const err = await res.json();
        showNotification(err.detail || 'Delete failed', 'error');
      }
    } catch (err) {
      showNotification('Network error', 'error');
    } finally {
      setLoading(false);
    }
  };

  // New Chat Submit Logic
  const submitQuery = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    const userMessage = { role: 'user', content: query };
    setChatHistory(prev => [...prev, userMessage]);
    const currentQuery = query;
    setQuery('');
    setQueryLoading(true);
    try {
      const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: currentQuery, course_id: selectedCourse?.id || null, max_chunks: 10 })
      });
      const data = await res.json();
      if (res.ok) {
        const botMessage = { 
          role: 'assistant', 
          content: data.answer,
          sources: data.sources,
          metrics: { time: data.processing_time, chunks: data.num_chunks }
        };
        setChatHistory(prev => [...prev, botMessage]);
      } else { showNotification(data.detail || 'Query failed', 'error'); }
    } catch (err) { showNotification('Network error', 'error'); } finally { setQueryLoading(false); }
  };

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-indigo-50 via-white to-purple-50 overflow-hidden">
      {/* Notification */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-6 py-4 rounded-lg shadow-xl flex items-center gap-3 animate-slide-in ${
          notification.type === 'error' ? 'bg-red-500' : 'bg-green-500'
        } text-white`}>
          {notification.type === 'error' ? <AlertCircle className="w-5 h-5" /> : <CheckCircle className="w-5 h-5" />}
          <span className="font-medium">{notification.message}</span>
          <button onClick={() => setNotification(null)} className="ml-2">
            <X className="w-5 h-5" />
          </button>
        </div>
      )}
  
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm z-40 flex-shrink-0">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl">
                <BookOpen className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                  Course RAG System
                </h1>
                <p className="text-sm text-gray-500">AI-Powered Course Assistant</p>
              </div>
            </div>
  
            {health && (
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg">
                  <div className={`w-2 h-2 rounded-full ${health.database_loaded ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-sm font-medium text-gray-700">
                    {health.database_loaded ? 'Database Ready' : 'Database Not Loaded'}
                  </span>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg">
                  <div className={`w-2 h-2 rounded-full ${health.llm_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-sm font-medium text-gray-700">
                    {health.llm_connected ? 'LLM Connected' : 'LLM Disconnected'}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>
  
      <div className="flex-1 overflow-hidden max-w-7xl w-full mx-auto px-6 py-4">
        <div className="h-full grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Sidebar */}
          <div className="flex flex-col gap-4 h-full overflow-hidden">
            {/* Stats Card */}
            {stats && (
              <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100 flex-shrink-0">
                <div className="flex items-center gap-2 mb-4">
                  <BarChart3 className="w-5 h-5 text-indigo-600" />
                  <h2 className="text-lg font-bold text-gray-900">Statistics</h2>
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between items-center p-3 bg-indigo-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Total Courses</span>
                    <span className="text-lg font-bold text-indigo-600">{stats.total_courses}</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-purple-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Total Materials</span>
                    <span className="text-lg font-bold text-purple-600">{stats.total_materials}</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-green-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Database Size</span>
                    <span className="text-lg font-bold text-green-600">{stats.database_size_mb} MB</span>
                  </div>
                </div>
              </div>
            )}
  
            {/* Courses List */}
            <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100 flex-1 min-h-0 flex flex-col">
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex-shrink-0">Courses</h2>
              <div className="space-y-2 flex-1 overflow-y-auto min-h-0">
                {courses.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-8">No courses yet</p>
                ) : (
                  courses.map(course => (
                    <div
                      key={course.id}
                      onClick={() => setSelectedCourse(course)}
                      role="button"
                      tabIndex={0}
                      className={`w-full text-left p-4 rounded-xl transition-all cursor-pointer ${
                        selectedCourse?.id === course.id
                          ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg'
                          : 'bg-gray-50 hover:bg-gray-100 text-gray-900'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-semibold">{course.name}</h3>
                          <p
                            className={`text-xs mt-1 ${
                              selectedCourse?.id === course.id ? 'text-indigo-100' : 'text-gray-500'
                            }`}
                          >
                            {course.materials_count} materials
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteCourse(course.id);
                          }}
                          className="p-1 hover:bg-white/20 rounded"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
  
            {/* Rebuild Button */}
            <button
              onClick={rebuildDatabase}
              disabled={loading}
              className="w-full bg-gradient-to-r from-green-500 to-emerald-600 text-white py-3 px-4 rounded-xl font-semibold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2 flex-shrink-0"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <RefreshCw className="w-5 h-5" />}
              Rebuild Database
            </button>
          </div>
  
          {/* Main Content */}
          <div className="lg:col-span-2 h-full flex flex-col min-h-0">
            {/* Tabs */}
            <div className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden flex flex-col h-full">
              <div className="flex border-b border-gray-200 flex-shrink-0">
                {['query', 'create', 'upload'].map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 py-4 px-6 font-semibold transition-all ${
                      activeTab === tab
                        ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {tab === 'query' && <div className="flex items-center justify-center gap-2"><Search className="w-4 h-4" />Query</div>}
                    {tab === 'create' && <div className="flex items-center justify-center gap-2"><Plus className="w-4 h-4" />Create Course</div>}
                    {tab === 'upload' && <div className="flex items-center justify-center gap-2"><Upload className="w-4 h-4" />Add Materials</div>}
                  </button>
                ))}
              </div>
  
              <div className="flex-1 min-h-0 flex flex-col p-6">
                
                {/* --- CHAT INTERFACE (QUERY TAB) --- */}
                {activeTab === 'query' && (
                  <div className="flex flex-col flex-1 min-h-0 bg-white rounded-xl border border-gray-200 shadow-inner overflow-hidden">
                    
                    {/* 1. Chat Header */}
                    <div className="p-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <Bot className="w-5 h-5 text-indigo-600" />
                        <span className="font-medium text-gray-700">AI Assistant</span>
                      </div>
                      {selectedCourse ? (
                        <span className="text-xs px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full font-medium">
                          Context: {selectedCourse.name}
                        </span>
                      ) : (
                        <span className="text-xs px-3 py-1 bg-gray-200 text-gray-600 rounded-full">
                          Global Context
                        </span>
                      )}
                    </div>
  
                    {/* 2. Messages Area */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-6 bg-gray-50/50 min-h-0">
                      {chatHistory.length === 0 && (
                        <div className="flex flex-col items-center justify-center text-gray-400 space-y-4 min-h-full">
                          <BookOpen className="w-12 h-12 opacity-20" />
                          <p>Select a course and ask a question to get started.</p>
                        </div>
                      )}
  
                      {chatHistory.map((msg, index) => (
                        <div 
                          key={index} 
                          className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
                        >
                          {/* Avatar */}
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                            msg.role === 'user' ? 'bg-indigo-600' : 'bg-emerald-600'
                          }`}>
                            {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
                          </div>
  
                          {/* Message Bubble */}
                          <div className={`max-w-[85%] space-y-2`}>
                            <div className={`p-4 rounded-2xl shadow-sm ${
                              msg.role === 'user' 
                                ? 'bg-indigo-600 text-white rounded-tr-none' 
                                : 'bg-white border border-gray-200 text-gray-800 rounded-tl-none'
                            }`}>
                              
                              {/* Rendering du contenu : Markdown + Latex */}
                              {msg.role === 'user' ? (
                                <p className="whitespace-pre-wrap leading-relaxed text-sm">{msg.content}</p>
                              ) : (
                                <div className="text-sm markdown-body prose prose-sm max-w-none">
                                  <ReactMarkdown 
                                    remarkPlugins={[remarkMath]} 
                                    rehypePlugins={[rehypeKatex]}
                                    components={{
                                      a: ({node, ...props}) => (
                                        <a {...props} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline" />
                                      )
                                    }}
                                  >
                                    {msg.content}
                                  </ReactMarkdown>
                                </div>
                              )}
  
                            </div>
  
                            {/* Sources & Metrics (AI Only) */}
                            {msg.role === 'assistant' && (msg.sources || msg.metrics) && (
                              <div className="flex flex-col gap-2 animate-fade-in">
                                 {/* Metrics */}
                                 {msg.metrics && (
                                   <div className="flex gap-3 text-xs text-gray-400 pl-1">
                                      <span>⏱ {msg.metrics.time.toFixed(2)}s</span>
                                      <span>📚 {msg.metrics.chunks} chunks</span>
                                   </div>
                                 )}
                                 {/* Sources List */}
                                 {msg.sources && msg.sources.length > 0 && (
                                   <div className="bg-white border border-gray-200 rounded-lg p-3 text-xs text-gray-600">
                                      <span className="font-semibold block mb-1">Sources Used:</span>
                                      <ul className="list-disc list-inside space-y-1">
                                        {msg.sources.map((src, i) => (
                                          <li key={i} className="truncate max-w-md">{src}</li>
                                        ))}
                                      </ul>
                                   </div>
                                 )}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
  
                      {/* Loading Indicator */}
                      {queryLoading && (
                        <div className="flex gap-4">
                          <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center flex-shrink-0">
                            <Bot className="w-5 h-5 text-white" />
                          </div>
                          <div className="bg-white border border-gray-200 p-4 rounded-2xl rounded-tl-none shadow-sm flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                            <span className="text-sm text-gray-500">Thinking...</span>
                          </div>
                        </div>
                      )}
                      <div ref={messagesEndRef} />
                    </div>
  
                    {/* 3. Input Area */}
                    <div className="p-4 bg-white border-t border-gray-200">
                      <div className="flex gap-3">
                        <input
                          type="text"
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && submitQuery(e)}
                          placeholder="Ask something about your courses..."
                          disabled={queryLoading}
                          className="flex-1 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
                        />
                        <button
                          onClick={submitQuery}
                          disabled={queryLoading || !query.trim()}
                          className="p-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl hover:shadow-lg disabled:opacity-50 transition-all flex items-center justify-center"
                        >
                          <Send className="w-5 h-5" />
                        </button>
                      </div>
                      <p className="text-xs text-center text-gray-400 mt-2">
                        AI can make mistakes. Please verify important information.
                      </p>
                    </div>
                  </div>
                )}
  
                {/* --- CREATE COURSE TAB --- */}
                {activeTab === 'create' && (
                  <div className="space-y-4 overflow-y-auto">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Course Name *
                      </label>
                      <input
                        type="text"
                        value={newCourse.name}
                        onChange={(e) => setNewCourse({...newCourse, name: e.target.value})}
                        placeholder="e.g., Machine Learning Fundamentals"
                        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>
  
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Description
                      </label>
                      <textarea
                        value={newCourse.description}
                        onChange={(e) => setNewCourse({...newCourse, description: e.target.value})}
                        placeholder="Brief description of the course..."
                        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                        rows={3}
                      />
                    </div>
  
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Category
                      </label>
                      <select
                        value={newCourse.category}
                        onChange={(e) => setNewCourse({...newCourse, category: e.target.value})}
                        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      >
                        <option value="General">General</option>
                        <option value="Computer Science">Computer Science</option>
                        <option value="Mathematics">Mathematics</option>
                        <option value="Science">Science</option>
                        <option value="Business">Business</option>
                        <option value="Arts">Arts</option>
                      </select>
                    </div>
  
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        createCourse(e);
                      }}
                      disabled={loading}
                      className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white py-3 px-6 rounded-xl font-semibold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
                      Create Course
                    </button>
                  </div>
                )}
  
                {/* --- UPLOAD MATERIALS TAB --- */}
                {activeTab === 'upload' && (
                  <div className="space-y-6 overflow-y-auto">
                    {!selectedCourse ? (
                      <div className="text-center py-12">
                        <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                        <p className="text-gray-600">Please select a course first</p>
                      </div>
                    ) : (
                      <>
                        <div className="p-4 bg-indigo-50 rounded-lg">
                          <p className="text-sm text-indigo-700">
                            Adding materials to: <strong>{selectedCourse.name}</strong>
                          </p>
                        </div>
  
                        {/* File Upload */}
                        <div className="space-y-4">
                          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                            <Upload className="w-5 h-5" />
                            Upload File (PDF, TXT, MD)
                          </h3>
                          
                          <div>
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept=".pdf,.txt,.md"
                              onChange={(e) => setUploadFile(e.target.files[0])}
                              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            />
                          </div>
  
                          <div>
                            <input
                              type="text"
                              value={uploadTitle}
                              onChange={(e) => setUploadTitle(e.target.value)}
                              placeholder="Material title (optional)"
                              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            />
                          </div>
  
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              uploadMaterial(e);
                            }}
                            disabled={loading || !uploadFile}
                            className="w-full bg-gradient-to-r from-blue-500 to-cyan-600 text-white py-3 px-6 rounded-xl font-semibold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                          >
                            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                            Upload File
                          </button>
                        </div>
  
                        <div className="border-t border-gray-200 pt-6" />
  
                        {/* YouTube Upload */}
                        <div className="space-y-4">
                          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                            <Youtube className="w-5 h-5" />
                            Add YouTube Video
                          </h3>
                          
                          <div>
                            <input
                              type="url"
                              value={youtubeUrl}
                              onChange={(e) => setYoutubeUrl(e.target.value)}
                              placeholder="https://www.youtube.com/watch?v=..."
                              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            />
                          </div>
  
                          <div>
                            <input
                              type="text"
                              value={youtubeTitle}
                              onChange={(e) => setYoutubeTitle(e.target.value)}
                              placeholder="Video title (optional)"
                              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            />
                          </div>
  
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              addYoutubeVideo(e);
                            }}
                            disabled={loading || !youtubeUrl.trim()}
                            className="w-full bg-gradient-to-r from-red-500 to-pink-600 text-white py-3 px-6 rounded-xl font-semibold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                          >
                            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Youtube className="w-5 h-5" />}
                            Add YouTube Video
                          </button>
                        </div>
  
                        {/* Materials List */}
                        {selectedCourse.materials_count > 0 && (
                          <div className="mt-6">
                            <h3 className="font-semibold text-gray-900 mb-3">Course Materials</h3>
                            <div className="space-y-2">
                              <p className="text-sm text-gray-500">
                                {selectedCourse.materials_count} materials in this course
                              </p>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
  
      <style>{`
        @keyframes slide-in {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-slide-in {
          animation: slide-in 0.3s ease-out;
        }
        .animate-fade-in {
          animation: fade-in 0.4s ease-out;
        }
      `}</style>
    </div>
  );
}

export default App;