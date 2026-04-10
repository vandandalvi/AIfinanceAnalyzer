import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend, LineElement, PointElement } from 'chart.js';
import { Bar, Pie, Line } from 'react-chartjs-2';
import { API_ENDPOINTS } from '../config/api';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend, LineElement, PointElement);

function Dashboard() {
  const [data, setData] = useState(null);
  const [aiSuggestions, setAiSuggestions] = useState('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  const DASHBOARD_CACHE_KEY = 'dashboardDataV3';
  const AI_CACHE_KEY = 'aiInsightsV3';
  const CACHE_TTL_MS = 1000 * 60 * 5;

  useEffect(() => {
    fetchDashboardData();
    fetchAiSuggestions();
  }, []);

  const getCachedValue = (key) => {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed?.timestamp || Date.now() - parsed.timestamp > CACHE_TTL_MS) return null;
      return parsed.value;
    } catch {
      return null;
    }
  };

  const setCachedValue = (key, value) => {
    try {
      sessionStorage.setItem(key, JSON.stringify({ value, timestamp: Date.now() }));
    } catch {
      // ignore storage quota issues
    }
  };

  const fetchDashboardData = async () => {
    const forceRefresh = Boolean(location.state?.forceRefresh);

    if (forceRefresh) {
      sessionStorage.removeItem(DASHBOARD_CACHE_KEY);
    }

    const cached = getCachedValue(DASHBOARD_CACHE_KEY);
    if (cached && !forceRefresh) {
      setData(cached);
      setLoading(false);
      return;
    }

    try {
      let response;
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        try {
          response = await axios.post(API_ENDPOINTS.dashboard, {}, { timeout: 20000 });
          break;
        } catch (error) {
          if (attempt === 2) throw error;
        }
      }
      setData(response.data);
      setCachedValue(DASHBOARD_CACHE_KEY, response.data);
    } catch (error) {
      console.error('Dashboard data error:', error);
      // Add a delay before redirecting to allow user to see what happened
      setTimeout(() => {
        alert('No transaction data found. Please upload your CSV file first.');
        navigate('/');
      }, 1000);
    } finally {
      setLoading(false);
    }
  };

  const fetchAiSuggestions = async () => {
    const forceRefresh = Boolean(location.state?.forceRefresh);

    if (forceRefresh) {
      sessionStorage.removeItem(AI_CACHE_KEY);
    }

    const cachedInsights = getCachedValue(AI_CACHE_KEY);
    if (cachedInsights && !forceRefresh) {
      setAiSuggestions(cachedInsights);
      return;
    }

    try {
      const response = await axios.post(API_ENDPOINTS.chat, {
        query: 'Give me 3 quick insights about my spending patterns and top saving opportunities'
      }, { timeout: 25000 });
      setAiSuggestions(response.data.response);
      setCachedValue(AI_CACHE_KEY, response.data.response);
    } catch (error) {
      console.error('AI suggestions error:', error);
      setAiSuggestions('Unable to generate AI insights at the moment.');
    }
  };

  const handleExport = async (url, type) => {
    setExporting(type);
    try {
      const response = await axios.get(url, { responseType: 'blob', timeout: 30000 });
      const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = blobUrl;
      link.setAttribute('download', type === 'csv' ? 'transactions_export.csv' : 'finance_report.json');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
      console.error(`Export ${type} failed:`, error);
      alert('Export failed. Please try again.');
    } finally {
      setExporting('');
    }
  };

  const healthScore = data?.healthScore || { score: 0, grade: 'D', factors: [], monthly: [] };
  const categoryIntelligence = data?.categoryIntelligence || {
    uncategorizedPercent: 0,
    uncategorizedCount: 0,
    topNeedsReview: [],
    suggestions: [],
  };

  const healthTone = useMemo(() => {
    if (healthScore.score >= 85) return 'text-emerald-600 bg-emerald-50';
    if (healthScore.score >= 70) return 'text-blue-600 bg-blue-50';
    if (healthScore.score >= 55) return 'text-amber-600 bg-amber-50';
    return 'text-red-600 bg-red-50';
  }, [healthScore.score]);

  const normalizeCategoryForInsights = (category = '') => {
    const c = String(category || '').trim();
    if (!c) return 'Other';

    if (c.startsWith('UPI - ')) return c.replace('UPI - ', '');
    if (['UPI Payments', 'Money Transfer', 'Credit Card'].includes(c)) return 'Transfers';
    if (c === 'Food & Dining') return 'Food';
    if (c === 'Cash Withdrawal') return 'Cash';
    return c;
  };

  const groupedCategories = useMemo(() => {
    const raw = data?.categories || [];
    const totals = raw.reduce((acc, row) => {
      const bucket = normalizeCategoryForInsights(row.category);
      const value = Math.abs(Number(row.total || 0));
      acc[bucket] = (acc[bucket] || 0) + value;
      return acc;
    }, {});

    return Object.entries(totals)
      .map(([category, total]) => ({ category, total }))
      .sort((a, b) => b.total - a.total);
  }, [data]);

  const transferBreakdown = useMemo(() => {
    const raw = data?.categories || [];
    const transferRows = raw.filter((row) => ['UPI Payments', 'Money Transfer', 'Credit Card'].includes(String(row.category || '')));

    const labelMap = {
      'UPI Payments': 'UPI (Generic/Unknown)',
      'Money Transfer': 'Bank Transfer',
      'Credit Card': 'Card Payment',
    };

    const totals = transferRows.reduce((acc, row) => {
      const label = labelMap[row.category] || row.category;
      const value = Math.abs(Number(row.total || 0));
      acc[label] = (acc[label] || 0) + value;
      return acc;
    }, {});

    const items = Object.entries(totals)
      .map(([label, total]) => ({ label, total }))
      .sort((a, b) => b.total - a.total);

    const total = items.reduce((sum, item) => sum + item.total, 0);
    return { items, total };
  }, [data]);

  const quickInsights = useMemo(() => {
    const top = groupedCategories[0];
    const monthlyTotals = (data?.monthly || []).map((m) => Math.abs(Number(m.total || 0)));
    const avgMonth = monthlyTotals.length
      ? monthlyTotals.reduce((s, v) => s + v, 0) / monthlyTotals.length
      : 0;
    const net = Number(data?.reportSummary?.net || 0);
    return {
      topCategory: top ? `${top.category} (₹${Math.round(top.total).toLocaleString()})` : 'No category data',
      avgMonthlyBurn: `₹${Math.round(avgMonth).toLocaleString()}`,
      netStatus: net >= 0 ? `+₹${Math.round(net).toLocaleString()}` : `-₹${Math.round(Math.abs(net)).toLocaleString()}`,
    };
  }, [groupedCategories, data]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Analyzing your finances...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">No data found. Please upload a CSV file first.</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            Upload CSV
          </button>
        </div>
      </div>
    );
  }

  const categoryData = {
    labels: groupedCategories.map(c => c.category),
    datasets: [{
      label: 'Spending by Category (₹)',
      data: groupedCategories.map(c => Math.abs(c.total)),
      backgroundColor: [
        '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
        '#06B6D4', '#F97316', '#84CC16', '#EC4899', '#6B7280'
      ],
      borderWidth: 0
    }]
  };

  const monthlyData = {
    labels: data.monthly?.map(m => m.month) || [],
    datasets: [{
      label: 'Monthly Spending (₹)',
      data: data.monthly?.map(m => Math.abs(m.total)) || [],
      backgroundColor: '#3B82F6',
      borderColor: '#1D4ED8',
      borderWidth: 2,
      fill: false,
      tension: 0.4
    }]
  };

  const topMerchantsData = {
    labels: data.topMerchants?.map(m => m.merchant) || [],
    datasets: [{
      label: 'Top Merchants (₹)',
      data: data.topMerchants?.map(m => Math.abs(m.total)) || [],
      backgroundColor: '#10B981',
      borderRadius: 8
    }]
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="w-full px-4 py-4 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              <div className="w-8 h-8 bg-indigo-600 text-white rounded-lg flex items-center justify-center min-w-[32px]">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 text-center sm:text-left">Finance Dashboard</h1>
            </div>
            <div className="flex flex-wrap justify-center gap-2 sm:gap-3 w-full sm:w-auto">
              <button
                onClick={() => navigate('/advanced-analytics')}
                className="px-3 sm:px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center justify-center space-x-2 flex-grow sm:flex-grow-0 text-sm sm:text-base"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span>Advanced Analytics</span>
              </button>
              <button
                onClick={() => navigate('/chat')}
                className="px-3 sm:px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center justify-center space-x-2 flex-grow sm:flex-grow-0 text-sm sm:text-base"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span>Financial Advisor(AI)</span>
              </button>
              <button
                onClick={() => handleExport(API_ENDPOINTS.exportCsv, 'csv')}
                disabled={exporting === 'csv'}
                className="px-3 sm:px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-60 flex-grow sm:flex-grow-0 text-sm sm:text-base"
              >
                {exporting === 'csv' ? 'Exporting...' : 'Export CSV'}
              </button>
              <button
                onClick={() => handleExport(API_ENDPOINTS.exportReport, 'report')}
                disabled={exporting === 'report'}
                className="px-3 sm:px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 disabled:opacity-60 flex-grow sm:flex-grow-0 text-sm sm:text-base"
              >
                {exporting === 'report' ? 'Exporting...' : 'Export Report'}
              </button>
              <button
                onClick={() => navigate('/')}
                className="px-3 sm:px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 flex-grow sm:flex-grow-0 text-sm sm:text-base"
              >
                Upload New CSV
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full px-3 py-6 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
        {/* Stats Overview */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <div className="flex items-center">
              <div className="p-2 bg-red-100 rounded-lg">
                <svg className="w-5 h-5 lg:w-6 lg:h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
              </div>
              <div className="ml-3 lg:ml-4">
                <p className="text-xs lg:text-sm font-medium text-gray-500">Total Spending</p>
                <p className="text-lg lg:text-2xl font-bold text-gray-900">₹{data.totalSpending?.toLocaleString() || 0}</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 rounded-lg">
                <svg className="w-5 h-5 lg:w-6 lg:h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l-1 4h-12l-1-4z" />
                </svg>
              </div>
              <div className="ml-3 lg:ml-4">
                <p className="text-xs lg:text-sm font-medium text-gray-500">Categories</p>
                <p className="text-lg lg:text-2xl font-bold text-gray-900">{data.totalCategories || 0}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <div className="flex items-center">
              <div className="p-2 bg-green-100 rounded-lg">
                <svg className="w-5 h-5 lg:w-6 lg:h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1" />
                </svg>
              </div>
              <div className="ml-3 lg:ml-4">
                <p className="text-xs lg:text-sm font-medium text-gray-500">Avg. Transaction</p>
                <p className="text-lg lg:text-2xl font-bold text-gray-900">₹{data.avgTransaction?.toLocaleString() || 0}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <div className="flex items-center">
              <div className="p-2 bg-purple-100 rounded-lg">
                <svg className="w-5 h-5 lg:w-6 lg:h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <div className="ml-3 lg:ml-4">
                <p className="text-xs lg:text-sm font-medium text-gray-500">Transactions</p>
                <p className="text-lg lg:text-2xl font-bold text-gray-900">{data.totalTransactions || 0}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Top Spend Bucket</p>
            <p className="mt-2 text-base lg:text-lg font-semibold text-gray-900">{quickInsights.topCategory}</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Average Monthly Burn</p>
            <p className="mt-2 text-base lg:text-lg font-semibold text-gray-900">{quickInsights.avgMonthlyBurn}</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Net Cashflow</p>
            <p className="mt-2 text-base lg:text-lg font-semibold text-gray-900">{quickInsights.netStatus}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 mb-8">
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-900">Monthly Health Score</h3>
              <span className={`px-3 py-1 rounded-full text-sm font-bold ${healthTone}`}>
                {healthScore.score}/100 • {healthScore.grade}
              </span>
            </div>
            <div className="space-y-2 mb-4">
              {(healthScore.factors || []).slice(0, 4).map((factor) => (
                <div key={factor.name} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">{factor.name}</span>
                  <span className={`font-semibold ${factor.impact >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {factor.impact >= 0 ? '+' : ''}{factor.impact}
                  </span>
                </div>
              ))}
            </div>
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Recent Monthly Scores</p>
              <div className="flex flex-wrap gap-2">
                {(healthScore.monthly || []).slice(-6).map((m) => (
                  <span key={m.month} className="px-2.5 py-1 rounded-lg bg-gray-100 text-xs text-gray-700">
                    {m.month}: {m.score}
                  </span>
                ))}
                {(healthScore.monthly || []).length === 0 && (
                  <span className="text-sm text-gray-500">Not enough monthly data yet.</span>
                )}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">Category Intelligence v2</h3>
            <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200">
              <p className="text-sm text-amber-800 font-medium">
                Uncategorized: {categoryIntelligence.uncategorizedCount} txns ({categoryIntelligence.uncategorizedPercent}%)
              </p>
            </div>
            <div className="mb-4">
              <p className="text-sm font-medium text-gray-700 mb-2">Needs Review</p>
              <div className="space-y-2">
                {(categoryIntelligence.topNeedsReview || []).slice(0, 3).map((item) => (
                  <div key={item.Description} className="text-sm text-gray-600 flex items-center justify-between">
                    <span className="truncate pr-3">{item.Description}</span>
                    <span className="font-semibold text-gray-800">₹{Math.round(item.total || 0)}</span>
                  </div>
                ))}
                {(categoryIntelligence.topNeedsReview || []).length === 0 && (
                  <p className="text-sm text-gray-500">Great job — categories are mostly clean.</p>
                )}
              </div>
            </div>
            <ul className="list-disc pl-5 space-y-1 text-sm text-gray-600">
              {(categoryIntelligence.suggestions || []).slice(0, 2).map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8 mb-8">
          {/* Category Pie Chart */}
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Spending by Category</h3>
            <div className="h-64 lg:h-80">
              <Pie data={categoryData} options={{ responsive: true, maintainAspectRatio: false }} />
            </div>
            {transferBreakdown.total > 0 && (
              <div className="mt-4 border-t border-gray-100 pt-3">
                <p className="text-sm font-semibold text-gray-800 mb-2">Transfers breakdown</p>
                <div className="space-y-1.5">
                  {transferBreakdown.items.map((item) => {
                    const pct = transferBreakdown.total > 0 ? (item.total / transferBreakdown.total) * 100 : 0;
                    return (
                      <div key={item.label} className="flex items-center justify-between text-xs sm:text-sm text-gray-600">
                        <span>{item.label}</span>
                        <span className="font-medium text-gray-800">₹{Math.round(item.total).toLocaleString()} ({pct.toFixed(0)}%)</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Monthly Line Chart */}
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Monthly Spending Trend</h3>
            <div className="h-64 lg:h-80">
              <Line data={monthlyData} options={{ responsive: true, maintainAspectRatio: false }} />
            </div>
          </div>

          {/* Top Merchants Chart */}
          <div className="bg-white rounded-xl shadow-sm p-4 lg:p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Top Merchants</h3>
            <div className="h-64 lg:h-80">
              <Bar data={topMerchantsData} options={{ responsive: true, maintainAspectRatio: false, indexAxis: 'y' }} />
            </div>
          </div>
        </div>

        {/* AI Insights */}
        <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl p-6">
          <div className="flex items-center mb-4">
            <div className="w-8 h-8 bg-indigo-600 text-white rounded-lg flex items-center justify-center mr-3">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-900">AI Insights</h3>
          </div>
          <div className="bg-white rounded-lg p-4 mb-4">
            <p className="text-gray-700 whitespace-pre-wrap">{aiSuggestions}</p>
          </div>
          <button
            onClick={() => navigate('/chat')}
            className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center space-x-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <span>Ask More Questions</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;