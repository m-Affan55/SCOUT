class DOMExtractor:
    @staticmethod
    def get_extraction_script() -> str:
        return """
        (() => {
            const tree = [];
            let index = 1;

            function extractFromDocument(doc, iframeIndex) {
                const elements = doc.querySelectorAll('input:not([type="hidden"]), textarea, select, button, a');

                elements.forEach(el => {
                    // Skip hidden or disabled elements
                    if (el.disabled || el.offsetParent === null) return;
                    
                    const tag = el.tagName.toLowerCase();
                    const type = el.getAttribute('type');
                    
                    // For links, skip ones with no text and no meaningful href
                    if (tag === 'a') {
                        const href = el.getAttribute('href') || '';
                        const text = el.innerText.trim();
                        if (!text || href === '#' || href === '' || href.startsWith('javascript:')) return;
                    }
                    
                    let label = '';
                    if (el.labels && el.labels.length > 0) {
                        label = el.labels[0].innerText.trim();
                    } else if (el.hasAttribute('aria-label')) {
                        label = el.getAttribute('aria-label');
                    } else if (tag === 'button' || tag === 'a') {
                        label = el.innerText.trim();
                    }
                    
                    let context = '';
                    // We need *something* to identify the element
                    if (!label && !el.placeholder && !el.id && !el.name && tag !== 'button' && tag !== 'a') {
                        if (el.previousElementSibling && el.previousElementSibling.innerText) {
                            context = el.previousElementSibling.innerText.trim();
                        }
                        if (!context && el.parentElement && el.parentElement.innerText) {
                            context = el.parentElement.innerText.trim();
                        }
                        if (context) {
                            context = context.replace(/\\n/g, ' ').substring(0, 100).trim();
                        }
                        
                        if (!context) return;
                    }
                    
                    const elementData = {
                        index: index++,
                        tag: tag,
                        type: type || undefined,
                        id: el.id || undefined,
                        name: el.name || undefined,
                        placeholder: el.placeholder || undefined,
                        label: label || undefined,
                        context: context || undefined,
                        value: el.value || undefined,
                    };
                    
                    // Add href for links so the LLM can see where they go
                    if (tag === 'a') {
                        const href = el.getAttribute('href') || '';
                        elementData.href = href;
                    }
                    
                    if (tag === 'select') {
                        const options = Array.from(el.options).map(opt => opt.text.trim());
                        elementData.options = options;
                    }
                    
                    // Track which iframe the element belongs to
                    if (iframeIndex !== undefined) {
                        elementData.iframe_index = iframeIndex;
                    }
                    
                    // Build CSS selector
                    let selector = el.id ? `#${CSS.escape(el.id)}` : null;
                    if (!selector && el.name) {
                        const escapedName = el.name.replace(/"/g, '\\"');
                        selector = `${tag}[name="${escapedName}"]`;
                    }
                    if (!selector) {
                        let path = [];
                        let current = el;
                        while (current && current.tagName !== 'HTML') {
                            let step = current.tagName.toLowerCase();
                            if (current.id) {
                                step += `#${CSS.escape(current.id)}`;
                                path.unshift(step);
                                break;
                            }
                            
                            let siblingIndex = 1;
                            let sibling = current.previousElementSibling;
                            while (sibling) {
                                if (sibling.tagName === current.tagName) siblingIndex++;
                                sibling = sibling.previousElementSibling;
                            }
                            if (siblingIndex > 1) {
                                step += `:nth-of-type(${siblingIndex})`;
                            }
                            path.unshift(step);
                            current = current.parentElement;
                        }
                        selector = path.join(' > ');
                    }
                    elementData.selector = selector;
                    
                    tree.push(elementData);
                });
            }

            // Extract from main document
            extractFromDocument(document, undefined);
            
            // Extract from same-origin iframes
            const iframes = document.querySelectorAll('iframe');
            iframes.forEach((iframe, idx) => {
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (iframeDoc) {
                        extractFromDocument(iframeDoc, idx);
                    }
                } catch(e) {
                    // Cross-origin iframe, skip silently
                }
            });
            
            return tree;
        })()
        """

    @staticmethod
    def format_tree_for_llm(tree: list[dict]) -> str:
        lines = []
        for el in tree:
            line = f"[{el['index']}] <{el['tag']}"
            if el.get('type'): line += f' type="{el["type"]}"'
            if el.get('label'): line += f' label="{el["label"]}"'
            if el.get('placeholder'): line += f' placeholder="{el["placeholder"]}"'
            if el.get('name'): line += f' name="{el["name"]}"'
            if el.get('context'): line += f' context="{el["context"]}"'
            # Show current value so the LLM knows which fields are already filled
            if el.get('value') and el['tag'] not in ('button', 'a'):
                line += f' value="{el["value"]}"'
            line += ">"
            
            if el.get('options'):
                line += f" options: {el['options']}"
            elif el['tag'] in ('button', 'a'):
                line += f" \"{el.get('label', '')}\""
                
            lines.append(line)
            
        return "\n".join(lines)

dom_extractor = DOMExtractor()
