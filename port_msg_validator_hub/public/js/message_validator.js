class MessageValidator {
      constructor() {
        this.xmlInput = document.getElementById('xml-input');
        this.parseBtn = document.getElementById('parse-btn');
        this.clearBtn = document.getElementById('clear-btn');
        this.loading = document.getElementById('loading');
        this.resultsContainer = document.getElementById('results-container');
        this.emptyState = document.getElementById('empty-state');
        
        this.setupEventListeners();
      }

      setupEventListeners() {
        this.parseBtn.addEventListener('click', () => this.validateMessage());
        this.clearBtn.addEventListener('click', () => this.clearForm());
        this.xmlInput.addEventListener('keydown', (e) => {
          if (e.ctrlKey && e.key === 'Enter') {
            this.validateMessage();
          }
        });
      }

      async validateMessage() {
        const xmlContent = this.xmlInput.value.trim();
        
        if (!xmlContent) {
          this.showError('Please paste a message to validate');
          return;
        }

        this.parseBtn.disabled = true;
        this.loading.style.display = 'block';
        this.resultsContainer.innerHTML = '';
        this.emptyState.style.display = 'none';

        try {
          const response = await frappe.call({
            method: 'port_msg_validator_hub.msg_validator.validate_message',
            args: { xml_string: xmlContent },
            async: true
          });

          this.parseBtn.disabled = false;
          this.loading.style.display = 'none';

          if (response.message) {
            console.log("response", response)
            this.displayResults(response.message);
          }
        } catch (error) {
          this.parseBtn.disabled = false;
          this.loading.style.display = 'none';
          this.showError('Validation failed: ' + error.message);
        }
      }

      displayResults(result) {
          console.log("result", result)
          const isValid = result.valid;
          const errorCount = result.error_count || 0;
          const errors = result.errors || {};
          const parsedMessage = result.parsed_message || null;

        // Helper to recursively render object as HTML table with error highlighting
        const renderTable = (obj, path = []) => {
          if (typeof obj !== 'object' || obj === null) {
            return `<span style="color: #495057;">${obj}</span>`;
          }
          
          if (Array.isArray(obj)) {
            return obj.map((item, idx) => renderTable(item, [...path, idx.toString()])).join('<hr style="border: 0; border-top: 1px dashed #dee2e6; margin: 10px 0;">');
          }

          const errorPaths = result.error_paths || [];
          const isErrorPath = (p) => errorPaths.some(ep => JSON.stringify(ep) === JSON.stringify(p));

          let rows = '';
          for (const [key, value] of Object.entries(obj)) {
            if (key.startsWith('@')) continue; // Skip attributes if any
            
            const currentPath = [...path, key];
            const hasError = isErrorPath(currentPath);
            
            rows += `<tr class="${hasError ? 'error-row' : ''}">
                      <td>${key.replace(/_/g, ' ')}</td>
                      <td>${renderTable(value, currentPath)}</td>
                    </tr>`;
          }
          return `<table class="parsed-data-table">
                    <tbody>${rows}</tbody>
                  </table>`;
        };

        let badgesHtml = '';
          
          if (parsedMessage) {
              const msgType = parsedMessage.header ? parsedMessage.header.message_type : 'Unknown';
              badgesHtml += `<div class="badge-custom badge-msg-type"><i class="fas fa-file-code"></i> ${msgType}</div>`;
              
              // Check for Document_Type in MSG2701
              if (msgType && msgType.includes('2701')) {
                  const docType = parsedMessage.contents && parsedMessage.contents.XML ? parsedMessage.contents.XML.Document_Type : null;
                  if (docType === 'I') {
                      badgesHtml += `<div class="badge-custom badge-import"><i class="fas fa-ship"></i> Import</div>`;
                  } else if (docType === 'E') {
                      badgesHtml += `<div class="badge-custom badge-export"><i class="fas fa-plane-departure"></i> Export</div>`;
                  }
              }
          }

        let html = `
          <div class="result-card ${isValid ? '' : 'error'} fade-in">
            <div class="result-header">
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <div class="result-status">
                  <div class="status-icon ${isValid ? 'status-success' : 'status-error'}">
                    ${isValid ? '✓' : '✕'}
                  </div>
                  <span>${isValid ? 'Validation Passed' : 'Validation Failed'}</span>
                </div>
                ${badgesHtml ? `<div class="badge-container">${badgesHtml}</div>` : ''}
              </div>
              ${!isValid ? `<div class="error-counter">${errorCount} Error${errorCount !== 1 ? 's' : ''}</div>` : ''}
            </div>
            <div class="result-body">
        `;

        if (isValid) {
          html += `
            <div style="color: var(--success-color); font-weight: 600;">
              <i class="fas fa-check-circle"></i> Message structure is valid and ready for processing.
            </div>
          `;
        } else {
          // Show errors by category
          const errorCategories = {
            'structural_errors': '⚠️ Structural Errors',
            'missing_required': '❌ Missing Required Fields',
            'type_errors': '🔤 Type Errors',
            'length_errors': '📏 Length Errors',
            'invalid_values': '⛔ Invalid Values'
          };

          for (const [category, label] of Object.entries(errorCategories)) {
            if (errors[category] && errors[category].length > 0) {
              html += `
                <div class="error-section">
                  <div class="error-section-title">
                    ${label}
                  </div>
                  <ul class="error-list">
                    ${errors[category].map(error => `<li>${error}</li>`).join('')}
                  </ul>
                </div>
              `;
            }
          }
        }

        // Show parsed message content for both valid and invalid results
        if (parsedMessage) {
          const header = parsedMessage.header;
          const contents = parsedMessage.contents;
          
          let sectionsHtml = '';
          
          // Header section
          if (header) {
            sectionsHtml += `
              <div class="section-divider">
                <span><i class="fas fa-info-circle"></i> Message Information (Header)</span>
              </div>
              <div class="data-section">
                ${renderTable(header, ['header'])}
              </div>
            `;
          }
          
          // Render all sections in contents (Transaction, XML, EDI, etc.)
          if (contents) {
            for (const [key, value] of Object.entries(contents)) {
              // Skip empty or null sections
              if (!value || (typeof value === 'object' && Object.keys(value).length === 0)) continue;
              
              let label = key.replace(/_/g, ' ');
              let icon = 'fa-database';
              
              // Custom icons and labels for known sections
              if (key === 'Transaction') {
                icon = 'fa-exchange-alt';
                label = 'Transaction Details';
              } else if (key === 'XML') {
                icon = 'fa-code';
                label = 'Business Content (XML)';
              } else if (key === 'EDI') {
                icon = 'fa-file-alt';
                label = 'EDI Data';
              }
              
              sectionsHtml += `
                <div class="section-divider">
                  <span><i class="fas ${icon}"></i> ${label}</span>
                </div>
                <div class="data-section">
                  ${renderTable(value, ['contents', key])}
                </div>
              `;
            }
          }

          html += `
            <div class="data-display-container">
              ${sectionsHtml}
            </div>
          `;
        }

        html += `
            </div>
          </div>
        `;

        this.resultsContainer.innerHTML = html;
      }

      showError(message) {
        const html = `
          <div class="result-card error fade-in">
            <div class="result-header">
              <div class="result-status">
                <div class="status-icon status-error">!</div>
                <span>Error</span>
              </div>
            </div>
            <div class="result-body">
              <div style="color: var(--danger-color);">
                <i class="fas fa-exclamation-circle"></i> ${message}
              </div>
            </div>
          </div>
        `;
        this.resultsContainer.innerHTML = html;
      }

      clearForm() {
        this.xmlInput.value = '';
        this.resultsContainer.innerHTML = '';
        this.emptyState.style.display = 'block';
        this.xmlInput.focus();
      }
}

// Initialize validator when page loads
frappe.ready(() => {
    new MessageValidator();
});
