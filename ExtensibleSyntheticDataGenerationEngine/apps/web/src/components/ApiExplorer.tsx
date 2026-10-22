import React, { useState, useEffect } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { Server, ChevronLeft, ChevronRight, RefreshCw, Copy, Check } from 'lucide-react';

export const ApiExplorer: React.FC = () => {
  const { generationResult, entities } = useSchemaStore();

  const [selectedEntity, setSelectedEntity] = useState<string>('');
  const [limit, setLimit] = useState<number>(10);
  const [offset, setOffset] = useState<number>(0);
  const [apiResponse, setApiResponse] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const schemaId = generationResult?.schema_id;

  useEffect(() => {
    if (entities.length > 0 && !selectedEntity) {
      setSelectedEntity(entities[0].name);
    }
  }, [entities, selectedEntity]);

  const fetchMockData = async () => {
    if (!schemaId || !selectedEntity) return;

    setIsLoading(true);
    try {
      const url = `http://localhost:8000/api/v1/mock/${schemaId}/${selectedEntity}?limit=${limit}&offset=${offset}`;
      const res = await fetch(url);
      const data = await res.json();
      setApiResponse(data);
    } catch (err) {
      console.error('Failed to fetch from mock API', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (schemaId && selectedEntity) {
      fetchMockData();
    }
  }, [schemaId, selectedEntity, limit, offset]);

  if (!schemaId) {
    return (
      <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800 space-y-2 text-slate-500">
        <Server className="w-8 h-8 mx-auto text-slate-600" />
        <p className="text-sm">No active Mock API instance.</p>
        <p className="text-xs">Generate a schema first to mount dynamic DuckDB endpoints.</p>
      </div>
    );
  }

  const currentUrl = `http://localhost:8000/api/v1/mock/${schemaId}/${selectedEntity}?limit=${limit}&offset=${offset}`;

  const handleCopy = () => {
    navigator.clipboard.writeText(currentUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const totalRecords = apiResponse?.pagination?.total_records || 0;
  const hasMore = apiResponse?.pagination?.has_more || false;

  return (
    <div className="space-y-5">
      
      {/* Controls Bar */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <span>Dynamic Mock REST API</span>
              <span className="text-xs font-mono text-cyan-300 font-normal">
                (DuckDB Backed)
              </span>
            </h2>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-400">Entity Endpoint:</label>
            <select
              value={selectedEntity}
              onChange={(e) => {
                setSelectedEntity(e.target.value);
                setOffset(0);
              }}
              className="text-xs bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-white font-mono focus:outline-none focus:border-cyan-500"
            >
              {entities.map((e) => (
                <option key={e.name} value={e.name}>
                  /api/v1/mock/{schemaId}/{e.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* URL Pill & Copy Button */}
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 font-mono text-xs text-cyan-300 overflow-x-auto flex items-center justify-between">
            <span>GET {currentUrl}</span>
          </div>
          <button
            onClick={handleCopy}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Copy URL"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>
          <button
            onClick={fetchMockData}
            disabled={isLoading}
            className="p-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Pagination Bar */}
        <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
          <div className="flex items-center gap-2">
            <span>Page Size:</span>
            <select
              value={limit}
              onChange={(e) => {
                setLimit(parseInt(e.target.value));
                setOffset(0);
              }}
              className="bg-slate-950 border border-slate-800 rounded px-2 py-0.5 text-white font-mono"
            >
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
            </select>
            <span className="text-slate-500 font-mono ml-2">
              Showing {totalRecords === 0 ? 0 : offset + 1} - {Math.min(offset + limit, totalRecords)} of {totalRecords}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className={`p-1.5 rounded border transition ${
                offset === 0
                  ? 'border-slate-800 text-slate-600 cursor-not-allowed'
                  : 'border-slate-700 bg-slate-800 text-white hover:bg-slate-700'
              }`}
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="font-mono text-white text-xs px-2">
              Page {Math.floor(offset / limit) + 1}
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={!hasMore}
              className={`p-1.5 rounded border transition ${
                !hasMore
                  ? 'border-slate-800 text-slate-600 cursor-not-allowed'
                  : 'border-slate-700 bg-slate-800 text-white hover:bg-slate-700'
              }`}
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </div>

      {/* Response Display */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
            HTTP 200 OK — JSON Response Envelope
          </span>
          <span className="text-[11px] font-mono text-emerald-400">
            {apiResponse?.data?.length || 0} records in payload
          </span>
        </div>

        <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800/80 font-mono text-xs text-cyan-300 max-h-[460px] overflow-auto whitespace-pre">
          {apiResponse ? JSON.stringify(apiResponse, null, 2) : '// Loading response...'}
        </pre>
      </div>

    </div>
  );
};
