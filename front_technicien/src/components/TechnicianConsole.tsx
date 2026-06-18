import React, { useEffect, useState, useRef, Component } from 'react';
import {
  Settings,
  Activity,
  Users,
  Calendar,
  Terminal,
  Wifi,
  WifiOff } from
'lucide-react';
export function TechnicianConsole() {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [wsUrl, setWsUrl] = useState('ws://localhost:8000/ws/pointages');
  const [activeTab, setActiveTab] = useState<
    'config' | 'admin' | 'stream' | 'suivi' | 'simulator'>(
    'config');
  const [isConnected, setIsConnected] = useState(false);
  const [serverConfig, setServerConfig] = useState<any>(null);
  useEffect(() => {
    const ws = baseUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    setWsUrl(`${ws}/ws/pointages`);
  }, [baseUrl]);
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${baseUrl}/health`);
        if (res.ok) {
          setIsConnected(true);
          const configRes = await fetch(`${baseUrl}/config`);
          if (configRes.ok) {
            const data = await configRes.json();
            setServerConfig(data);
          }
        } else {
          setIsConnected(false);
        }
      } catch {
        setIsConnected(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, [baseUrl]);
  const tabs = [
  {
    id: 'config' as const,
    label: 'Terminal Configurator',
    icon: Settings
  },
  {
    id: 'admin' as const,
    label: 'Employee Admin',
    icon: Users
  },
  {
    id: 'stream' as const,
    label: 'Live Stream',
    icon: Activity
  },
  {
    id: 'suivi' as const,
    label: 'Suivi',
    icon: Calendar
  },
  {
    id: 'simulator' as const,
    label: 'Simulator',
    icon: Terminal
  }];

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#4580C4] via-[#3A6FB0] to-[#2F5E9C] p-4">
      <div className="max-w-[1600px] mx-auto">
        <div className="bg-gradient-to-b from-white/95 to-white/90 rounded-t-lg border border-white/40 shadow-lg backdrop-blur-sm p-4 mb-1">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {isConnected ?
              <Wifi className="w-5 h-5 text-green-600" /> :

              <WifiOff className="w-5 h-5 text-red-600" />
              }
              <span className="text-sm font-semibold select-text">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <div className="flex-1 flex items-center gap-2">
              <label className="text-sm font-medium select-text">
                Base URL:
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="flex-1 px-3 py-1.5 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
            </div>
            {serverConfig &&
            <div className="text-xs text-gray-600 select-text">
                Format: {serverConfig.terminal_format} | Pause:{' '}
                {serverConfig.pause_mode}
              </div>
            }
          </div>
        </div>

        {/* Tab Bar */}
        <div className="bg-gradient-to-b from-[#E8F0F8] to-[#D0E0F0] border-x border-white/40 shadow-sm flex gap-1 px-2 py-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-2 px-4 py-2 rounded-t
                  transition-all select-text
                  ${isActive ? 'bg-gradient-to-b from-white to-gray-50 border border-b-0 border-gray-300 shadow-sm' : 'bg-gradient-to-b from-gray-100/50 to-gray-200/50 hover:from-white/80 hover:to-gray-100/80'}
                `}>
                
                <Icon className="w-4 h-4" />
                <span className="text-sm font-medium">{tab.label}</span>
              </button>);

          })}
        </div>

        <div className="bg-gradient-to-b from-white to-gray-50 rounded-b-lg border border-white/40 shadow-2xl backdrop-blur-sm p-6 min-h-[700px]">
          {activeTab === 'config' &&
          <TerminalConfiguratorTab baseUrl={baseUrl} />
          }
          {activeTab === 'admin' && <EmployeeAdminTab baseUrl={baseUrl} />}
          {activeTab === 'stream' && <LiveStreamTab wsUrl={wsUrl} />}
          {activeTab === 'suivi' && <SuiviTab baseUrl={baseUrl} />}
          {activeTab === 'simulator' &&
          <SimulatorTab baseUrl={baseUrl} wsUrl={wsUrl} />
          }
        </div>
      </div>
    </div>);

}
function TerminalConfiguratorTab({ baseUrl }: {baseUrl: string;}) {
  const [models, setModels] = useState<any>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [modelDetails, setModelDetails] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any>(null);
  const [testResult, setTestResult] = useState<any>(null);
  // Editable configuration state
  const [envOverrides, setEnvOverrides] = useState<Record<string, string>>({});
  const [testHost, setTestHost] = useState('localhost');
  // Editable image URL for the selected model (default derived from backend fields, fully overridable)
  const [imageUrl, setImageUrl] = useState('');
  useEffect(() => {
    fetch(`${baseUrl}/configurator/models`).
    then((r) => r.json()).
    then(setModels).
    catch(console.error);
  }, [baseUrl]);
  const handleSelectModel = async (key: string) => {
    if (!key) {
      setSelectedModel(null);
      setModelDetails(null);
      return;
    }
    setSelectedModel(key);
    setTestResult(null);
    try {
      const details = await fetch(`${baseUrl}/configurator/models/${key}`).then(
        (r) => r.json()
      );
      setModelDetails(details);
      setEnvOverrides(details.env_config || {});
      setImageUrl(
        getUnsplashImage(details.model?.manufacturer, details.model?.name)
      );
    } catch (err) {
      console.error(err);
    }
  };
  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      const res = await fetch(
        `${baseUrl}/configurator/search?query=${encodeURIComponent(searchQuery)}`
      );
      const data = await res.json();
      setSearchResults(data);
    } catch (err) {
      console.error(err);
    }
  };
  const handleTestConnection = async () => {
    if (!selectedModel) return;
    try {
      const res = await fetch(
        `${baseUrl}/configurator/test/${selectedModel}?host=${encodeURIComponent(testHost)}`,
        {
          method: 'POST'
        }
      );
      const data = await res.json();
      setTestResult(data);
    } catch (err) {
      setTestResult({
        connected: false,
        message: String(err)
      });
    }
  };
  const handleApplyConfig = async () => {
    if (!selectedModel) return;
    try {
      const res = await fetch(
        `${baseUrl}/configurator/models/${selectedModel}/apply`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(envOverrides)
        }
      );
      const data = await res.json();
      alert(data.message || 'Configuration applied successfully');
    } catch (err) {
      alert('Error applying configuration: ' + err);
    }
  };
  const handleOverrideChange = (key: string, value: string) => {
    setEnvOverrides((prev) => ({
      ...prev,
      [key]: value
    }));
  };
  const getUnsplashImage = (manufacturer?: string, name?: string) => {
    const query = encodeURIComponent(
      `${manufacturer || ''} ${name || ''} biometric terminal device`.trim()
    );
    return `https://source.unsplash.com/featured/400x300/?${query}`;
  };
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-blue-50 to-blue-100 border border-blue-200 rounded p-4">
        <h2 className="text-lg font-bold text-blue-900 mb-2 select-text">
          Terminal Configurator
        </h2>
        <p className="text-sm text-blue-800 select-text">
          Search, select, and fully configure biometric terminal models.
        </p>
      </div>

      {/* Selection Controls: Dropdown AND Search */}
      <div className="bg-white border border-gray-300 rounded p-4 space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Dropdown Select */}
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1 select-text text-gray-700">
              Select Model from List:
            </label>
            <select
              value={selectedModel || ''}
              onChange={(e) => handleSelectModel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
              
              <option value="">-- Select a terminal model --</option>
              {models?.models &&
              Object.entries(models.models).map(
                ([key, model]: [string, any]) =>
                <option key={key} value={key}>
                      {model.manufacturer} - {model.name}
                    </option>

              )}
            </select>
          </div>

          {/* Search Input */}
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1 select-text text-gray-700">
              Or Search Models:
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="e.g. ZKTeco, Hikvision..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
              <button
                onClick={handleSearch}
                className="px-4 py-2 bg-gradient-to-b from-blue-500 to-blue-600 text-white rounded hover:from-blue-600 hover:to-blue-700 select-text">
                
                Search
              </button>
            </div>
          </div>
        </div>

        {/* Search Results */}
        {searchResults && searchResults.results &&
        <div className="mt-4 border-t border-gray-200 pt-4">
            <h3 className="text-sm font-semibold mb-2 select-text text-gray-700">
              Search Results ({searchResults.count})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {searchResults.results.map((r: any) =>
            <div
              key={r.key}
              onClick={() => handleSelectModel(r.key)}
              className={`p-3 border rounded cursor-pointer select-text transition-colors flex items-center gap-3 ${selectedModel === r.key ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
              
                  <img
                src={getUnsplashImage(r.manufacturer, r.name)}
                alt={r.name}
                onError={(e) => {
                  ;(e.currentTarget as HTMLImageElement).style.visibility =
                  'hidden';
                }}
                className="w-12 h-12 object-cover rounded border border-gray-300 bg-gray-100" />
              
                  <div>
                    <div className="font-medium text-sm select-text line-clamp-1">
                      {r.name}
                    </div>
                    <div className="text-xs text-gray-600 select-text">
                      {r.manufacturer}
                    </div>
                  </div>
                </div>
            )}
            </div>
          </div>
        }
      </div>

      {/* Selected Model Details & Configuration */}
      {modelDetails &&
      <div className="bg-white border border-gray-300 rounded p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Left Column: Info & Image */}
            <div className="lg:w-1/3 space-y-4">
              <div className="rounded overflow-hidden border border-gray-300 shadow-sm bg-gray-100">
                <img
                src={imageUrl}
                alt={modelDetails.model.name}
                onError={(e) => {
                  ;(e.currentTarget as HTMLImageElement).style.visibility =
                  'hidden';
                }}
                className="w-full h-48 object-cover bg-gray-100" />
              
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-500 uppercase mb-1 select-text">
                  Image URL (override)
                </label>
                <input
                type="text"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="Paste any image URL..."
                className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
              </div>

              <div>
                <h3 className="font-bold text-lg text-gray-900 select-text leading-tight">
                  {modelDetails.model.name}
                </h3>
                <div className="mt-3 space-y-2 text-sm select-text">
                  <div className="flex justify-between border-b border-gray-100 pb-1">
                    <span className="text-gray-500">Manufacturer</span>
                    <span className="font-medium">
                      {modelDetails.model.manufacturer}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-gray-100 pb-1">
                    <span className="text-gray-500">Default Port</span>
                    <span className="font-medium">
                      {modelDetails.model.port}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-gray-100 pb-1">
                    <span className="text-gray-500">Protocol</span>
                    <span className="font-medium">
                      {modelDetails.model.protocol}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-gray-100 pb-1">
                    <span className="text-gray-500">Data Format</span>
                    <span className="font-medium uppercase">
                      {modelDetails.model.data_format}
                    </span>
                  </div>
                </div>
              </div>

              {modelDetails.model.documentation_url &&
            <div className="pt-2">
                  <label className="block text-xs font-semibold text-gray-500 uppercase mb-1 select-text">
                    Documentation URL
                  </label>
                  <a
                href={modelDetails.model.documentation_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-xs text-blue-600 underline break-all mb-1 select-text">
                
                    {modelDetails.model.documentation_url}
                  </a>
                </div>
            }
            </div>

            {/* Right Column: Editable Configuration & Testing */}
            <div className="lg:w-2/3 space-y-6">
              {/* Editable Env Config */}
              <div className="bg-gray-50 border border-gray-200 rounded p-4">
                <h4 className="font-semibold text-gray-800 mb-3 select-text flex items-center gap-2">
                  <Settings className="w-4 h-4" />
                  Terminal Configuration (Editable)
                </h4>
                <div className="space-y-3">
                  {Object.entries(envOverrides).map(([key, value]) =>
                <div
                  key={key}
                  className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                  
                      <label
                    className="sm:w-1/3 text-sm font-medium text-gray-700 select-text truncate"
                    title={key}>
                    
                        {key}
                      </label>
                      <input
                    type="text"
                    value={value}
                    onChange={(e) =>
                    handleOverrideChange(key, e.target.value)
                    }
                    className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white" />
                  
                    </div>
                )}
                </div>
                <div className="mt-4 flex justify-end">
                  <button
                  onClick={handleApplyConfig}
                  className="px-6 py-2 bg-gradient-to-b from-blue-500 to-blue-600 text-white font-medium rounded shadow-sm hover:from-blue-600 hover:to-blue-700 select-text">
                  
                    Apply Configuration
                  </button>
                </div>
              </div>

              {/* Connection Testing */}
              <div className="bg-gray-50 border border-gray-200 rounded p-4">
                <h4 className="font-semibold text-gray-800 mb-3 select-text flex items-center gap-2">
                  <Wifi className="w-4 h-4" />
                  Test Connection
                </h4>
                <div className="flex flex-col sm:flex-row gap-3 items-end">
                  <div className="flex-1 w-full">
                    <label className="block text-sm font-medium text-gray-700 mb-1 select-text">
                      Target Host / IP
                    </label>
                    <input
                    type="text"
                    value={testHost}
                    onChange={(e) => setTestHost(e.target.value)}
                    placeholder="e.g. 192.168.1.100 or localhost"
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white" />
                  
                  </div>
                  <button
                  onClick={handleTestConnection}
                  className="px-6 py-2 bg-gradient-to-b from-green-500 to-green-600 text-white font-medium rounded shadow-sm hover:from-green-600 hover:to-green-700 select-text whitespace-nowrap">
                  
                    Run Test
                  </button>
                </div>

                {testResult &&
              <div
                className={`mt-4 p-3 rounded border ${testResult.connected ? 'bg-green-100 border-green-300' : 'bg-red-100 border-red-300'}`}>
                
                    <div
                  className={`font-bold select-text ${testResult.connected ? 'text-green-800' : 'text-red-800'}`}>
                  
                      {testResult.connected ?
                  '✓ Connection Successful' :
                  '✗ Connection Failed'}
                    </div>
                    <div className="text-sm mt-1 text-gray-800 select-text">
                      {testResult.message}
                    </div>
                    {testResult.troubleshoot && !testResult.connected &&
                <div className="mt-2 text-xs text-red-700 select-text">
                        <strong>Troubleshooting:</strong>
                        <ul className="list-disc list-inside mt-1">
                          {testResult.troubleshoot.checklist?.map(
                      (item: string, i: number) =>
                      <li key={i}>{item}</li>

                    )}
                        </ul>
                      </div>
                }
                  </div>
              }
              </div>
            </div>
          </div>
        </div>
      }
    </div>);

}
// Employee Admin Tab
function EmployeeAdminTab({ baseUrl }: {baseUrl: string;}) {
  const [employees, setEmployees] = useState<any[]>([]);
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const [formData, setFormData] = useState({
    id_pointeuse: '',
    prenom: '',
    nom: '',
    poste: '',
    departement: '',
    email: '',
    telephone: '',
    heure_arrivee_prevue: '08:00',
    heure_depart_prevue: '17:00',
    duree_pause_min: 60
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const loadEmployees = async () => {
    try {
      const res = await fetch(`${baseUrl}/admin/employes/liste?actif_only=true`);
      const data = await res.json();
      setEmployees(data.employes || []);
    } catch (err) {
      console.error(err);
    }
  };
  const loadSyncStatus = async () => {
    try {
      const res = await fetch(`${baseUrl}/admin/sync-status`);
      const data = await res.json();
      setSyncStatus(data);
    } catch (err) {
      console.error(err);
    }
  };
  useEffect(() => {
    loadEmployees();
    loadSyncStatus();
  }, [baseUrl]);
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const url = editingId ?
      `${baseUrl}/admin/employes/${editingId}` :
      `${baseUrl}/admin/employes/enregistrer`;
      const method = editingId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        alert(editingId ? 'Employee updated' : 'Employee registered');
        setFormData({
          id_pointeuse: '',
          prenom: '',
          nom: '',
          poste: '',
          departement: '',
          email: '',
          telephone: '',
          heure_arrivee_prevue: '08:00',
          heure_depart_prevue: '17:00',
          duree_pause_min: 60
        });
        setEditingId(null);
        loadEmployees();
        loadSyncStatus();
      } else {
        const err = await res.json();
        alert(err.detail || 'Error');
      }
    } catch (err) {
      alert('Error: ' + err);
    }
  };
  const handleEdit = (emp: any) => {
    setFormData({
      id_pointeuse: emp.id_pointeuse,
      prenom: emp.prenom,
      nom: emp.nom,
      poste: emp.poste || '',
      departement: emp.departement || '',
      email: emp.email || '',
      telephone: emp.telephone || '',
      heure_arrivee_prevue: emp.heure_arrivee_prevue || '08:00',
      heure_depart_prevue: emp.heure_depart_prevue || '17:00',
      duree_pause_min: emp.duree_pause_min || 60
    });
    setEditingId(emp.id);
  };
  const handleDelete = async (id: string) => {
    if (!confirm('Deactivate this employee?')) return;
    try {
      await fetch(`${baseUrl}/admin/employes/${id}`, {
        method: 'DELETE'
      });
      loadEmployees();
      loadSyncStatus();
    } catch (err) {
      alert('Error: ' + err);
    }
  };
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-green-50 to-green-100 border border-green-200 rounded p-4">
        <h2 className="text-lg font-bold text-green-900 mb-2 select-text">
          Employee Administration
        </h2>
        <p className="text-sm text-green-800 select-text">
          Register and manage employees with pointeuse synchronization
        </p>
      </div>

      {/* Sync Status */}
      {syncStatus &&
      <div className="bg-white border border-gray-300 rounded p-4">
          <h3 className="font-semibold mb-3 select-text">
            Synchronization Status
          </h3>
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white p-4 rounded">
              <div className="text-2xl font-bold select-text">
                {syncStatus.total_employes}
              </div>
              <div className="text-sm select-text">Total Employees</div>
            </div>
            <div className="bg-gradient-to-br from-green-500 to-green-600 text-white p-4 rounded">
              <div className="text-2xl font-bold select-text">
                {syncStatus.avec_id_pointeuse}
              </div>
              <div className="text-sm select-text">With ID Pointeuse</div>
            </div>
            <div className="bg-gradient-to-br from-orange-500 to-orange-600 text-white p-4 rounded">
              <div className="text-2xl font-bold select-text">
                {syncStatus.sans_id_pointeuse}
              </div>
              <div className="text-sm select-text">Without ID</div>
            </div>
            <div className="bg-gradient-to-br from-purple-500 to-purple-600 text-white p-4 rounded">
              <div className="text-2xl font-bold select-text">
                {syncStatus.sync_ratio_pct}%
              </div>
              <div className="text-sm select-text">Sync Ratio</div>
            </div>
          </div>
        </div>
      }

      <div className="grid grid-cols-2 gap-4">
        {/* Form */}
        <div className="bg-white border border-gray-300 rounded p-4">
          <h3 className="font-semibold mb-3 select-text">
            {editingId ? 'Edit Employee' : 'New Employee'}
          </h3>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1 select-text">
                ID Pointeuse *
              </label>
              <input
                type="text"
                value={formData.id_pointeuse}
                onChange={(e) =>
                setFormData({
                  ...formData,
                  id_pointeuse: e.target.value
                })
                }
                required
                className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Prénom *
                </label>
                <input
                  type="text"
                  value={formData.prenom}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    prenom: e.target.value
                  })
                  }
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Nom *
                </label>
                <input
                  type="text"
                  value={formData.nom}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    nom: e.target.value
                  })
                  }
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Poste
                </label>
                <input
                  type="text"
                  value={formData.poste}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    poste: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Département
                </label>
                <input
                  type="text"
                  value={formData.departement}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    departement: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Email
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    email: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Téléphone
                </label>
                <input
                  type="tel"
                  value={formData.telephone}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    telephone: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Arrivée
                </label>
                <input
                  type="time"
                  value={formData.heure_arrivee_prevue}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    heure_arrivee_prevue: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Départ
                </label>
                <input
                  type="time"
                  value={formData.heure_depart_prevue}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    heure_depart_prevue: e.target.value
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Pause (min)
                </label>
                <input
                  type="number"
                  value={formData.duree_pause_min}
                  onChange={(e) =>
                  setFormData({
                    ...formData,
                    duree_pause_min: parseInt(e.target.value)
                  })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
                
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-gradient-to-b from-blue-500 to-blue-600 text-white rounded hover:from-blue-600 hover:to-blue-700 select-text">
                
                {editingId ? 'Update' : 'Register'}
              </button>
              {editingId &&
              <button
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setFormData({
                    id_pointeuse: '',
                    prenom: '',
                    nom: '',
                    poste: '',
                    departement: '',
                    email: '',
                    telephone: '',
                    heure_arrivee_prevue: '08:00',
                    heure_depart_prevue: '17:00',
                    duree_pause_min: 60
                  });
                }}
                className="px-4 py-2 bg-gradient-to-b from-gray-400 to-gray-500 text-white rounded hover:from-gray-500 hover:to-gray-600 select-text">
                
                  Cancel
                </button>
              }
            </div>
          </form>
        </div>

        {/* List */}
        <div className="bg-white border border-gray-300 rounded p-4">
          <h3 className="font-semibold mb-3 select-text">
            Registered Employees ({employees.length})
          </h3>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {employees.map((emp) =>
            <div
              key={emp.id}
              className="p-3 border border-gray-200 rounded hover:bg-gray-50">
              
                <div className="flex justify-between items-start">
                  <div className="flex-1 select-text">
                    <div className="font-medium">
                      {emp.prenom} {emp.nom}
                    </div>
                    <div className="text-sm text-gray-600">
                      ID: {emp.id_pointeuse}
                    </div>
                    <div className="text-xs text-gray-500">
                      {emp.poste || 'No position'} | {emp.email || 'No email'}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button
                    onClick={() => handleEdit(emp)}
                    className="px-3 py-1 text-xs bg-gradient-to-b from-blue-400 to-blue-500 text-white rounded hover:from-blue-500 hover:to-blue-600 select-text">
                    
                      Edit
                    </button>
                    <button
                    onClick={() => handleDelete(emp.id)}
                    className="px-3 py-1 text-xs bg-gradient-to-b from-red-400 to-red-500 text-white rounded hover:from-red-500 hover:to-red-600 select-text">
                    
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>);

}
// Live Stream Tab
function LiveStreamTab({ wsUrl }: {wsUrl: string;}) {
  const [events, setEvents] = useState<any[]>([]);
  const [config, setConfig] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents(data.events || []);
        setConfig(data.config || null);
      } catch (err) {
        console.error(err);
      }
    };
    return () => {
      ws.close();
    };
  }, [wsUrl]);
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-purple-50 to-purple-100 border border-purple-200 rounded p-4">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-bold text-purple-900 mb-2 select-text">
              Live Pointage Stream
            </h2>
            <p className="text-sm text-purple-800 select-text">
              Real-time events from biometric terminal
            </p>
          </div>
          <div
            className={`px-4 py-2 rounded font-semibold select-text ${isConnected ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}`}>
            
            {isConnected ? '● LIVE' : '○ DISCONNECTED'}
          </div>
        </div>
      </div>

      {config &&
      <div className="bg-white border border-gray-300 rounded p-4">
          <h3 className="font-semibold mb-2 select-text">
            Current Configuration
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm select-text">
            <div>
              <span className="font-medium">Pause Mode:</span>{' '}
              {config.pause_mode}
            </div>
            <div>
              <span className="font-medium">Pointage Mode:</span>{' '}
              {config.pointage_mode}
            </div>
          </div>
        </div>
      }

      <div className="bg-white border border-gray-300 rounded p-4">
        <h3 className="font-semibold mb-3 select-text">
          Recent Events ({events.length})
        </h3>
        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {events.length === 0 ?
          <div className="text-gray-500 text-center py-8 select-text">
              No events yet. Waiting for pointages...
            </div> :

          events.map((event, idx) =>
          <div
            key={idx}
            className={`p-3 border rounded select-text ${event.warning ? 'border-orange-300 bg-orange-50' : 'border-gray-200'}`}>
            
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="font-medium select-text">
                      <span className="text-blue-600">{event.action}</span> -{' '}
                      {event.employe_name}
                    </div>
                    <div className="text-sm text-gray-600 select-text">
                      {event.heure} | Status: {event.statut}
                    </div>
                    {event.warning &&
                <div className="text-sm text-orange-600 mt-1 select-text">
                        ⚠️ {event.warning}
                      </div>
                }
                  </div>
                  <div className="text-xs text-gray-500 select-text">
                    {event.timestamp}
                  </div>
                </div>
              </div>
          )
          }
        </div>
      </div>
    </div>);

}
// Suivi Tab
function SuiviTab({ baseUrl }: {baseUrl: string;}) {
  const [view, setView] = useState<'jour' | 'semaine' | 'mois'>('jour');
  const [dateStr, setDateStr] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [annee, setAnnee] = useState(new Date().getFullYear());
  const [mois, setMois] = useState(new Date().getMonth() + 1);
  const [data, setData] = useState<any>(null);
  const [employees, setEmployees] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${baseUrl}/admin/employes/liste?actif_only=true`).
    then((r) => r.json()).
    then((d) => setEmployees(d.employes || [])).
    catch(console.error);
  }, [baseUrl]);
  const handleFetch = async () => {
    try {
      let url = '';
      if (view === 'jour') {
        url = `${baseUrl}/suivi/jour${dateStr ? `?date_str=${dateStr}` : ''}`;
      } else if (view === 'semaine') {
        if (!employeeId) {
          alert('Select an employee for weekly view');
          return;
        }
        url = `${baseUrl}/suivi/employe/${employeeId}/semaine${dateStr ? `?date_ref=${dateStr}` : ''}`;
      } else {
        if (!employeeId) {
          alert('Select an employee for monthly view');
          return;
        }
        url = `${baseUrl}/suivi/employe/${employeeId}/mois?annee=${annee}&mois=${mois}`;
      }
      const res = await fetch(url);
      const result = await res.json();
      setData(result);
    } catch (err) {
      console.error(err);
      alert('Error fetching data');
    }
  };
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-indigo-50 to-indigo-100 border border-indigo-200 rounded p-4">
        <h2 className="text-lg font-bold text-indigo-900 mb-2 select-text">
          Suivi (Tracking)
        </h2>
        <p className="text-sm text-indigo-800 select-text">
          View attendance tracking by day, week, or month
        </p>
      </div>

      {/* Controls */}
      <div className="bg-white border border-gray-300 rounded p-4 space-y-3">
        <div className="flex gap-2">
          {(['jour', 'semaine', 'mois'] as const).map((v) =>
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-4 py-2 rounded select-text ${view === v ? 'bg-gradient-to-b from-blue-500 to-blue-600 text-white' : 'bg-gradient-to-b from-gray-200 to-gray-300 hover:from-gray-300 hover:to-gray-400'}`}>
            
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          )}
        </div>

        <div className="grid grid-cols-4 gap-3">
          {(view === 'semaine' || view === 'mois') &&
          <div>
              <label className="block text-sm font-medium mb-1 select-text">
                Employee
              </label>
              <select
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500">
              
                <option value="">Select...</option>
                {employees.map((emp) =>
              <option key={emp.id} value={emp.id}>
                    {emp.prenom} {emp.nom}
                  </option>
              )}
              </select>
            </div>
          }

          {view !== 'mois' &&
          <div>
              <label className="block text-sm font-medium mb-1 select-text">
                Date (YYYY-MM-DD)
              </label>
              <input
              type="date"
              value={dateStr}
              onChange={(e) => setDateStr(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
            
            </div>
          }

          {view === 'mois' &&
          <>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Year
                </label>
                <input
                type="number"
                value={annee}
                onChange={(e) => setAnnee(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 select-text">
                  Month
                </label>
                <input
                type="number"
                min="1"
                max="12"
                value={mois}
                onChange={(e) => setMois(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded select-text focus:outline-none focus:ring-2 focus:ring-blue-500" />
              
              </div>
            </>
          }

          <div className="flex items-end">
            <button
              onClick={handleFetch}
              className="w-full px-4 py-2 bg-gradient-to-b from-green-500 to-green-600 text-white rounded hover:from-green-600 hover:to-green-700 select-text">
              
              Fetch Data
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {data &&
      <div className="bg-white border border-gray-300 rounded p-4">
          <h3 className="font-semibold mb-3 select-text">Results</h3>
          <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto max-h-[500px] select-text">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      }
    </div>);

}
// Simulator Tab
function SimulatorTab({ baseUrl, wsUrl }: {baseUrl: string;wsUrl: string;}) {
  const simulatedEmployees = [
  {
    nom: 'Diallo',
    prenom: 'Mohamed',
    id_pointeuse: 'EMP001',
    horaire_arrivee: '08:00',
    horaire_depart: '17:00'
  },
  {
    nom: 'Ndiaye',
    prenom: 'Fatou',
    id_pointeuse: 'EMP002',
    horaire_arrivee: '08:30',
    horaire_depart: '17:30'
  },
  {
    nom: 'Cisse',
    prenom: 'Amadou',
    id_pointeuse: 'EMP003',
    horaire_arrivee: '07:45',
    horaire_depart: '16:45'
  }];

  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-yellow-50 to-yellow-100 border border-yellow-200 rounded p-4">
        <h2 className="text-lg font-bold text-yellow-900 mb-2 select-text">
          Terminal Simulator
        </h2>
        <p className="text-sm text-yellow-800 select-text">
          Run the biometric terminal simulator to test the system
        </p>
      </div>

      {/* Instructions */}
      <div className="bg-white border border-gray-300 rounded p-4">
        <h3 className="font-semibold mb-3 select-text">
          How to Run the Simulator
        </h3>
        <ol className="list-decimal list-inside space-y-2 text-sm select-text">
          <li>Ensure the backend server is running on {baseUrl}</li>
          <li>
            Register the 3 simulated employees below (if not already done)
          </li>
          <li>
            Open a terminal and run:{' '}
            <code className="bg-gray-100 px-2 py-1 rounded select-text">
              python -m pointage_prodac.terminal_simulator
            </code>
          </li>
          <li>
            The simulator will connect to localhost:9999 and send pointage
            events
          </li>
          <li>Watch the Live Stream tab for real-time events</li>
        </ol>
      </div>

      {/* Simulated Employees Reference */}
      <div className="bg-white border border-gray-300 rounded p-4">
        <h3 className="font-semibold mb-3 select-text">
          Simulated Employees (Hardcoded in Simulator)
        </h3>
        <div className="space-y-2">
          {simulatedEmployees.map((emp) =>
          <div
            key={emp.id_pointeuse}
            className="p-3 border border-gray-200 rounded select-text">
            
              <div className="font-medium">
                {emp.prenom} {emp.nom}
              </div>
              <div className="text-sm text-gray-600">
                ID Pointeuse: {emp.id_pointeuse}
              </div>
              <div className="text-xs text-gray-500">
                Schedule: {emp.horaire_arrivee} - {emp.horaire_depart}
              </div>
            </div>
          )}
        </div>
        <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
          <p className="text-sm text-blue-800 select-text">
            <strong>Important:</strong> These employees must be registered in
            the Employee Admin tab with the exact same ID Pointeuse values
            before running the simulator.
          </p>
        </div>
      </div>

      {/* Live Preview */}
      <div className="bg-white border border-gray-300 rounded p-4">
        <h3 className="font-semibold mb-3 select-text">Live Stream Preview</h3>
        <p className="text-sm text-gray-600 mb-3 select-text">
          Once the simulator is running, events will appear in the Live Stream
          tab. You can also monitor them here:
        </p>
        <div className="border border-gray-300 rounded p-3 bg-gray-50">
          <LiveStreamTab wsUrl={wsUrl} />
        </div>
      </div>
    </div>);

}