class DOMExtractor:
    @staticmethod
    def get_extraction_script() -> str:
        return """
        (() => {
            const elements = document.querySelectorAll('input:not([type="hidden"]), textarea, select, button, a');
            const tree = [];
            let index = 1;

            elements.forEach(el => {
                // Skip hidden or disabled elements
                if (el.disabled || el.offsetParent === null) return;
                
                // Skip elements without a useful role/text
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type');
                
                let label = '';
                if (el.labels && el.labels.length > 0) {
                    label = el.labels[0].innerText.trim();
                } else if (el.hasAttribute('aria-label')) {
                    label = el.getAttribute('aria-label');
                } else if (tag === 'button' || tag === 'a') {
                    label = el.innerText.trim();
                }
                
                // We need *something* to identify the element
                if (!label && !el.placeholder && !el.id && !el.name && tag !== 'button' && tag !== 'a') return;
                
                const elementData = {
                    index: index++,
                    tag: tag,
                    type: type || undefined,
                    id: el.id || undefined,
                    name: el.name || undefined,
                    placeholder: el.placeholder || undefined,
                    label: label || undefined,
                    value: el.value || undefined,
                };
                
                if (tag === 'select') {
                    const options = Array.from(el.options).map(opt => opt.text.trim());
                    elementData.options = options;
                }
                
                // Keep the exact css selector so we can map index back to it
                let selector = el.id ? `#${el.id}` : null;
                if (!selector && el.name) {
                    selector = `${tag}[name="${el.name}"]`;
                }
                if (!selector) {
                    // Fallback to a unique selector if possible or simple tag
                    // Not robust for complex pages, but works for simple forms
                    let path = [];
                    let current = el;
                    while (current && current.tagName !== 'HTML') {
                        let step = current.tagName.toLowerCase();
                        if (current.id) {
                            step += `#${current.id}`;
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
